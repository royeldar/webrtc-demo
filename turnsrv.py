#!/usr/bin/env python3
"""Minimal STUN + TURN server with shared-relay port multiplexing.

Implements just enough of RFC 5389 (STUN) and RFC 5766 (TURN) for a
WebRTC browser to do ICE: Binding, Allocate, Refresh, CreatePermission,
ChannelBind, Send/Data indications, and ChannelData framing. Long-term
credential auth (MESSAGE-INTEGRITY HMAC-SHA1).

Multiplexing: every allocation advertises the *same* relay address
(EXTERNAL_IP, RELAY_PORT) and a single shared UDP socket carries all
relay traffic. Inbound packets are routed to the owning allocation by
peer 5-tuple, which is registered on each outbound Send/ChannelData and
each CreatePermission/ChannelBind.

Stdlib only -- no external dependencies.
"""

import argparse
import hashlib
import hmac
import logging
import os
import secrets
import selectors
import socket
import struct
import sys
import threading
import time
import zlib
from collections import defaultdict, deque

LOG = logging.getLogger('turnsrv')

# ---------- STUN / TURN protocol constants ----------

MAGIC_COOKIE = 0x2112A442
MAGIC_COOKIE_BYTES = struct.pack('!I', MAGIC_COOKIE)
FINGERPRINT_XOR = 0x5354554E

# Message methods
M_BINDING            = 0x001
M_ALLOCATE           = 0x003
M_REFRESH            = 0x004
M_SEND               = 0x006
M_DATA               = 0x007
M_CREATE_PERMISSION  = 0x008
M_CHANNEL_BIND       = 0x009

# Message classes (encoded in bits 4 and 8 of the message type)
C_REQUEST    = 0x000
C_INDICATION = 0x010
C_RESPONSE   = 0x100
C_ERROR      = 0x110

# Attribute types
A_MAPPED_ADDRESS         = 0x0001
A_USERNAME               = 0x0006
A_MESSAGE_INTEGRITY      = 0x0008
A_ERROR_CODE             = 0x0009
A_CHANNEL_NUMBER         = 0x000C
A_LIFETIME               = 0x000D
A_XOR_PEER_ADDRESS       = 0x0012
A_DATA                   = 0x0013
A_REALM                  = 0x0014
A_NONCE                  = 0x0015
A_XOR_RELAYED_ADDRESS    = 0x0016
A_REQUESTED_TRANSPORT    = 0x0019
A_DONT_FRAGMENT          = 0x001A
A_XOR_MAPPED_ADDRESS     = 0x0020
A_SOFTWARE               = 0x8022
A_FINGERPRINT            = 0x8028

ADDR_FAMILY_V4 = 0x01

REQUESTED_TRANSPORT_UDP = 17

# Channel numbers per RFC 5766: 0x4000 .. 0x7FFE
CHANNEL_RANGE = (0x4000, 0x7FFE)


def msg_type(klass, method):
    return (
        ((method & 0xF80) << 2) |
        ((method & 0x070) << 1) |
        (method & 0x00F) |
        klass
    )


def parse_msg_type(t):
    method = (t & 0x000F) | ((t & 0x00E0) >> 1) | ((t & 0x3E00) >> 2)
    klass  = t & 0x0110
    return klass, method


def pad4(n):
    return (4 - (n % 4)) % 4


# ---------- Message decoding ----------

class StunMessage:
    __slots__ = ('klass', 'method', 'txid', 'attrs', 'integrity_pos', 'fingerprint_pos', 'raw')

    def __init__(self, klass, method, txid):
        self.klass = klass
        self.method = method
        self.txid = txid
        self.attrs = []  # list[(type, value_bytes)]
        self.integrity_pos = None
        self.fingerprint_pos = None
        self.raw = b''

    def get(self, attr_type):
        for t, v in self.attrs:
            if t == attr_type:
                return v
        return None

    def get_all(self, attr_type):
        return [v for t, v in self.attrs if t == attr_type]


def decode_message(data):
    if len(data) < 20:
        return None
    msg_type_raw, length, cookie = struct.unpack('!HHI', data[:8])
    if cookie != MAGIC_COOKIE:
        return None
    if len(data) < 20 + length:
        return None
    txid = data[8:20]
    klass, method = parse_msg_type(msg_type_raw)
    msg = StunMessage(klass, method, txid)
    msg.raw = data[:20 + length]
    pos = 20
    end = 20 + length
    while pos + 4 <= end:
        atype, alen = struct.unpack('!HH', data[pos:pos+4])
        avalue_start = pos + 4
        avalue_end = avalue_start + alen
        if avalue_end > end:
            return None
        avalue = data[avalue_start:avalue_end]
        if atype == A_MESSAGE_INTEGRITY:
            msg.integrity_pos = pos
        elif atype == A_FINGERPRINT:
            msg.fingerprint_pos = pos
        msg.attrs.append((atype, avalue))
        pos = avalue_end + pad4(alen)
    return msg


# ---------- Message encoding ----------

class MessageBuilder:
    __slots__ = ('klass', 'method', 'txid', 'parts')

    def __init__(self, klass, method, txid):
        self.klass = klass
        self.method = method
        self.txid = txid
        self.parts = []

    def add_attr(self, atype, value):
        self.parts.append((atype, value))

    def add_xor_address(self, atype, ip, port):
        # RFC 5389 §15.2 — IPv4 only here.
        xport = port ^ (MAGIC_COOKIE >> 16)
        ip_int = struct.unpack('!I', socket.inet_aton(ip))[0]
        xip = ip_int ^ MAGIC_COOKIE
        value = struct.pack('!BBHI', 0, ADDR_FAMILY_V4, xport, xip)
        self.add_attr(atype, value)

    def add_address(self, atype, ip, port):
        ip_bytes = socket.inet_aton(ip)
        value = struct.pack('!BBH', 0, ADDR_FAMILY_V4, port) + ip_bytes
        self.add_attr(atype, value)

    def add_error(self, code, reason):
        cls = code // 100
        num = code % 100
        reason_b = reason.encode('utf-8')
        value = struct.pack('!HBB', 0, cls, num) + reason_b
        self.add_attr(A_ERROR_CODE, value)

    def add_lifetime(self, seconds):
        self.add_attr(A_LIFETIME, struct.pack('!I', seconds))

    def add_string(self, atype, s):
        self.add_attr(atype, s.encode('utf-8') if isinstance(s, str) else s)

    def _encode_attrs(self, parts):
        out = bytearray()
        for atype, value in parts:
            out += struct.pack('!HH', atype, len(value))
            out += value
            out += b'\x00' * pad4(len(value))
        return bytes(out)

    def build(self, integrity_key=None, with_fingerprint=False):
        # MESSAGE-INTEGRITY (when present) is appended before any
        # FINGERPRINT and is computed over a header whose Length covers
        # the message up to and including the MESSAGE-INTEGRITY
        # attribute itself.
        body_no_auth = self._encode_attrs(self.parts)
        out = bytearray()
        out += struct.pack('!HHI', msg_type(self.klass, self.method),
                           len(body_no_auth), MAGIC_COOKIE)
        out += self.txid
        out += body_no_auth

        if integrity_key is not None:
            # Adjust header length to include the upcoming
            # MESSAGE-INTEGRITY (4 + 20 = 24 bytes)
            new_len = len(body_no_auth) + 24
            out[2:4] = struct.pack('!H', new_len)
            mac = hmac.new(integrity_key, bytes(out), hashlib.sha1).digest()
            out += struct.pack('!HH', A_MESSAGE_INTEGRITY, 20) + mac

        if with_fingerprint:
            new_len = len(out) - 20 + 8
            out[2:4] = struct.pack('!H', new_len)
            crc = zlib.crc32(bytes(out)) ^ FINGERPRINT_XOR
            out += struct.pack('!HHI', A_FINGERPRINT, 4, crc & 0xFFFFFFFF)

        return bytes(out)


def parse_xor_address(value, txid):
    if len(value) < 8:
        return None
    _, family, xport = struct.unpack('!BBH', value[:4])
    if family != ADDR_FAMILY_V4:
        return None
    port = xport ^ (MAGIC_COOKIE >> 16)
    xip = struct.unpack('!I', value[4:8])[0]
    ip_int = xip ^ MAGIC_COOKIE
    ip = socket.inet_ntoa(struct.pack('!I', ip_int))
    return ip, port


def parse_lifetime(value):
    if value is None or len(value) != 4:
        return None
    return struct.unpack('!I', value)[0]


# ---------- Auth ----------

def long_term_key(username, realm, password):
    return hashlib.md5(f'{username}:{realm}:{password}'.encode('utf-8')).digest()


def verify_integrity(raw, integrity_pos, key):
    # RFC 5389 §15.4 — recompute over the message with header Length
    # adjusted so that MESSAGE-INTEGRITY is the last attribute. Everything
    # past integrity_pos+24 (i.e. a trailing FINGERPRINT) is excluded.
    truncated = bytearray(raw[:integrity_pos + 24])
    body_len = len(truncated) - 20
    truncated[2:4] = struct.pack('!H', body_len)
    expected = hmac.new(key, bytes(truncated[:integrity_pos]), hashlib.sha1).digest()
    actual = bytes(raw[integrity_pos + 4:integrity_pos + 24])
    return hmac.compare_digest(expected, actual)


# ---------- Allocation state ----------

PERMISSION_LIFETIME = 300   # RFC 5766 §8
DEFAULT_LIFETIME    = 600
MAX_LIFETIME        = 3600
NONCE_LIFETIME      = 3600


class Allocation:
    __slots__ = ('client_addr', 'transport', 'tcp_conn', 'expires_at',
                 'permissions', 'channels', 'nonce', 'last_seen')

    def __init__(self, client_addr, transport, nonce, tcp_conn=None):
        self.client_addr = client_addr     # (ip, port) of the TURN client
        self.transport = transport          # 'udp' or 'tcp'
        self.tcp_conn = tcp_conn            # socket if transport == 'tcp'
        self.expires_at = time.monotonic() + DEFAULT_LIFETIME
        self.permissions = {}               # peer_ip -> expires_at
        self.channels = {}                  # channel_num -> (peer_ip, peer_port)
        self.nonce = nonce                  # bytes; client must echo this
        self.last_seen = time.monotonic()

    def has_permission(self, peer_ip):
        e = self.permissions.get(peer_ip)
        return e is not None and e > time.monotonic()

    def add_permission(self, peer_ip):
        self.permissions[peer_ip] = time.monotonic() + PERMISSION_LIFETIME


# ---------- Server ----------

class TurnServer:
    def __init__(self, listen_port, relay_port, external_ip,
                 realm, username, password):
        self.listen_port = listen_port
        self.relay_port = relay_port
        self.external_ip = external_ip
        self.realm = realm
        self.username = username
        self.password = password
        self.integrity_key = long_term_key(username, realm, password)

        # Allocations keyed by (transport, client_addr)
        self.allocations = {}
        # peer_addr -> Allocation, for shared-relay demux
        self.relay_routes = {}
        self.lock = threading.Lock()
        self.sel = selectors.DefaultSelector()

    # ----- socket setup -----

    def setup(self):
        self.udp_main = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_main.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_main.bind(('0.0.0.0', self.listen_port))

        self.tcp_main = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_main.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_main.bind(('0.0.0.0', self.listen_port))
        self.tcp_main.listen(64)
        self.tcp_main.setblocking(False)

        self.relay_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.relay_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.relay_sock.bind(('0.0.0.0', self.relay_port))

        self.udp_main.setblocking(False)
        self.relay_sock.setblocking(False)

        self.sel.register(self.udp_main, selectors.EVENT_READ, self._on_udp_main)
        self.sel.register(self.tcp_main, selectors.EVENT_READ, self._on_tcp_accept)
        self.sel.register(self.relay_sock, selectors.EVENT_READ, self._on_relay_inbound)

        LOG.info('listening: STUN/TURN UDP+TCP :%d, shared relay UDP :%d advertised %s:%d',
                 self.listen_port, self.relay_port,
                 self.external_ip, self.relay_port)

    # ----- main loop -----

    def serve(self):
        last_gc = time.monotonic()
        while True:
            for key, _ in self.sel.select(timeout=5):
                key.data(key.fileobj)
            now = time.monotonic()
            if now - last_gc > 10:
                self._gc(now)
                last_gc = now

    def _gc(self, now):
        with self.lock:
            stale = [k for k, a in self.allocations.items() if a.expires_at <= now]
            for k in stale:
                self._drop_allocation_locked(self.allocations[k])

    def _drop_allocation_locked(self, alloc):
        key = (alloc.transport, alloc.client_addr)
        self.allocations.pop(key, None)
        for peer in list(self.relay_routes.keys()):
            if self.relay_routes[peer] is alloc:
                del self.relay_routes[peer]
        if alloc.tcp_conn is not None:
            try:
                self.sel.unregister(alloc.tcp_conn)
            except (KeyError, ValueError):
                pass
            try:
                alloc.tcp_conn.close()
            except OSError:
                pass

    # ----- UDP STUN/TURN listener -----

    def _on_udp_main(self, sock):
        while True:
            try:
                data, addr = sock.recvfrom(65535)
            except BlockingIOError:
                return
            except OSError:
                return
            self._handle_main_datagram(data, addr, transport='udp', tcp_conn=None)

    # ----- TCP listener -----

    def _on_tcp_accept(self, sock):
        try:
            conn, addr = sock.accept()
        except BlockingIOError:
            return
        conn.setblocking(False)
        state = {'buf': bytearray(), 'addr': addr}
        self.sel.register(conn, selectors.EVENT_READ,
                          lambda c, st=state: self._on_tcp_data(c, st))

    def _on_tcp_data(self, conn, state):
        try:
            chunk = conn.recv(65535)
        except (BlockingIOError, ConnectionResetError):
            return
        except OSError:
            chunk = b''
        if not chunk:
            self._close_tcp(conn, state['addr'])
            return
        state['buf'].extend(chunk)
        buf = state['buf']
        # Frame STUN messages: header[20] + length, plus padding to 4 bytes
        # over TCP (RFC 5389 §7.2.2).
        while len(buf) >= 4:
            first = buf[0]
            if first < 0x40:
                # STUN message
                if len(buf) < 20:
                    return
                length = struct.unpack('!H', bytes(buf[2:4]))[0]
                total = 20 + length
                total += pad4(total)
                if len(buf) < total:
                    return
                msg_bytes = bytes(buf[:20 + length])
                del buf[:total]
                self._handle_main_datagram(msg_bytes, state['addr'],
                                           transport='tcp', tcp_conn=conn)
            elif 0x40 <= first <= 0x7F:
                # ChannelData frame on TCP
                if len(buf) < 4:
                    return
                _ch, length = struct.unpack('!HH', bytes(buf[:4]))
                total = 4 + length
                total += pad4(total)
                if len(buf) < total:
                    return
                frame = bytes(buf[:4 + length])
                del buf[:total]
                self._handle_channel_data(frame, state['addr'],
                                          transport='tcp', tcp_conn=conn)
            else:
                # Unrecognised; drop the connection rather than risk
                # desyncing.
                self._close_tcp(conn, state['addr'])
                return

    def _close_tcp(self, conn, addr):
        try:
            self.sel.unregister(conn)
        except (KeyError, ValueError):
            pass
        try:
            conn.close()
        except OSError:
            pass
        with self.lock:
            alloc = self.allocations.get(('tcp', addr))
            if alloc is not None:
                self._drop_allocation_locked(alloc)

    # ----- Main message dispatch -----

    def _send_main(self, payload, addr, transport, tcp_conn):
        if transport == 'udp':
            try:
                self.udp_main.sendto(payload, addr)
            except OSError:
                pass
        else:
            try:
                tcp_conn.sendall(payload)
            except OSError:
                self._close_tcp(tcp_conn, addr)

    def _handle_main_datagram(self, data, addr, transport, tcp_conn):
        if not data:
            return
        first = data[0]
        if 0x40 <= first <= 0x7F:
            # ChannelData over UDP
            self._handle_channel_data(data, addr, transport, tcp_conn)
            return
        msg = decode_message(data)
        if msg is None:
            return
        try:
            if msg.method == M_BINDING and msg.klass == C_REQUEST:
                self._handle_binding(msg, addr, transport, tcp_conn)
            elif msg.method == M_ALLOCATE and msg.klass == C_REQUEST:
                self._handle_allocate(msg, addr, transport, tcp_conn)
            elif msg.method == M_REFRESH and msg.klass == C_REQUEST:
                self._handle_refresh(msg, addr, transport, tcp_conn)
            elif msg.method == M_CREATE_PERMISSION and msg.klass == C_REQUEST:
                self._handle_create_permission(msg, addr, transport, tcp_conn)
            elif msg.method == M_CHANNEL_BIND and msg.klass == C_REQUEST:
                self._handle_channel_bind(msg, addr, transport, tcp_conn)
            elif msg.method == M_SEND and msg.klass == C_INDICATION:
                self._handle_send_indication(msg, addr, transport, tcp_conn)
            else:
                LOG.debug('unhandled message: cls=0x%x method=0x%x', msg.klass, msg.method)
        except Exception:
            LOG.exception('error while handling message method=0x%x', msg.method)

    # ----- STUN Binding -----

    def _handle_binding(self, msg, addr, transport, tcp_conn):
        b = MessageBuilder(C_RESPONSE, M_BINDING, msg.txid)
        b.add_xor_address(A_XOR_MAPPED_ADDRESS, addr[0], addr[1])
        self._send_main(b.build(), addr, transport, tcp_conn)

    # ----- TURN auth helper -----

    def _check_auth(self, msg, addr, transport, tcp_conn, require_alloc=False):
        """Return (alloc_or_None, ok). Sends the appropriate error response
        on failure and returns ok=False."""
        username = msg.get(A_USERNAME)
        realm = msg.get(A_REALM)
        nonce = msg.get(A_NONCE)
        if (msg.integrity_pos is None or username is None
                or realm is None or nonce is None):
            self._send_unauthenticated(msg, addr, transport, tcp_conn,
                                        code=401, reason='Unauthenticated')
            return None, False
        if username != self.username.encode('utf-8'):
            self._send_error(msg, addr, transport, tcp_conn, 401, 'Unauthenticated')
            return None, False
        if realm != self.realm.encode('utf-8'):
            self._send_error(msg, addr, transport, tcp_conn, 401, 'Wrong realm')
            return None, False
        if not verify_integrity(msg.raw, msg.integrity_pos, self.integrity_key):
            self._send_error(msg, addr, transport, tcp_conn, 401, 'Integrity failed')
            return None, False
        with self.lock:
            alloc = self.allocations.get((transport, addr))
            if alloc is not None:
                if alloc.nonce != bytes(nonce):
                    self._send_error(msg, addr, transport, tcp_conn,
                                     438, 'Stale nonce', nonce=alloc.nonce)
                    return None, False
                alloc.last_seen = time.monotonic()
        if require_alloc and alloc is None:
            self._send_error(msg, addr, transport, tcp_conn, 437, 'Allocation Mismatch')
            return None, False
        return alloc, True

    def _send_unauthenticated(self, msg, addr, transport, tcp_conn, code, reason):
        # 401 challenge: include REALM and NONCE so the client retries with creds.
        nonce = secrets.token_hex(16).encode('ascii')
        b = MessageBuilder(C_ERROR, msg.method, msg.txid)
        b.add_error(code, reason)
        b.add_string(A_REALM, self.realm)
        b.add_attr(A_NONCE, nonce)
        self._send_main(b.build(), addr, transport, tcp_conn)

    def _send_error(self, msg, addr, transport, tcp_conn, code, reason, nonce=None):
        b = MessageBuilder(C_ERROR, msg.method, msg.txid)
        b.add_error(code, reason)
        b.add_string(A_REALM, self.realm)
        if nonce is not None:
            b.add_attr(A_NONCE, nonce)
        self._send_main(b.build(integrity_key=self.integrity_key), addr, transport, tcp_conn)

    # ----- TURN Allocate -----

    def _handle_allocate(self, msg, addr, transport, tcp_conn):
        alloc, ok = self._check_auth(msg, addr, transport, tcp_conn)
        if not ok:
            return
        with self.lock:
            existing = self.allocations.get((transport, addr))
            if existing is not None:
                self._send_error(msg, addr, transport, tcp_conn, 437, 'Allocation Mismatch')
                return
            req_transport = msg.get(A_REQUESTED_TRANSPORT)
            if req_transport is None or req_transport[0] != REQUESTED_TRANSPORT_UDP:
                self._send_error(msg, addr, transport, tcp_conn, 442,
                                 'Unsupported Transport Protocol')
                return
            requested_lifetime = parse_lifetime(msg.get(A_LIFETIME)) or DEFAULT_LIFETIME
            lifetime = max(60, min(requested_lifetime, MAX_LIFETIME))
            alloc = Allocation(addr, transport, bytes(msg.get(A_NONCE)),
                               tcp_conn=tcp_conn)
            alloc.expires_at = time.monotonic() + lifetime
            self.allocations[(transport, addr)] = alloc
        b = MessageBuilder(C_RESPONSE, M_ALLOCATE, msg.txid)
        b.add_xor_address(A_XOR_RELAYED_ADDRESS, self.external_ip, self.relay_port)
        b.add_xor_address(A_XOR_MAPPED_ADDRESS, addr[0], addr[1])
        b.add_lifetime(lifetime)
        self._send_main(b.build(integrity_key=self.integrity_key),
                        addr, transport, tcp_conn)

    # ----- TURN Refresh -----

    def _handle_refresh(self, msg, addr, transport, tcp_conn):
        alloc, ok = self._check_auth(msg, addr, transport, tcp_conn, require_alloc=True)
        if not ok:
            return
        requested = parse_lifetime(msg.get(A_LIFETIME))
        if requested is None:
            requested = DEFAULT_LIFETIME
        if requested == 0:
            with self.lock:
                self._drop_allocation_locked(alloc)
            b = MessageBuilder(C_RESPONSE, M_REFRESH, msg.txid)
            b.add_lifetime(0)
            self._send_main(b.build(integrity_key=self.integrity_key),
                            addr, transport, tcp_conn)
            return
        lifetime = max(60, min(requested, MAX_LIFETIME))
        with self.lock:
            alloc.expires_at = time.monotonic() + lifetime
        b = MessageBuilder(C_RESPONSE, M_REFRESH, msg.txid)
        b.add_lifetime(lifetime)
        self._send_main(b.build(integrity_key=self.integrity_key),
                        addr, transport, tcp_conn)

    # ----- TURN CreatePermission -----

    def _handle_create_permission(self, msg, addr, transport, tcp_conn):
        alloc, ok = self._check_auth(msg, addr, transport, tcp_conn, require_alloc=True)
        if not ok:
            return
        peers = msg.get_all(A_XOR_PEER_ADDRESS)
        if not peers:
            self._send_error(msg, addr, transport, tcp_conn, 400, 'Bad Request')
            return
        with self.lock:
            for raw in peers:
                parsed = parse_xor_address(raw, msg.txid)
                if parsed is None:
                    continue
                alloc.add_permission(parsed[0])
        b = MessageBuilder(C_RESPONSE, M_CREATE_PERMISSION, msg.txid)
        self._send_main(b.build(integrity_key=self.integrity_key),
                        addr, transport, tcp_conn)

    # ----- TURN ChannelBind -----

    def _handle_channel_bind(self, msg, addr, transport, tcp_conn):
        alloc, ok = self._check_auth(msg, addr, transport, tcp_conn, require_alloc=True)
        if not ok:
            return
        ch_raw = msg.get(A_CHANNEL_NUMBER)
        peer_raw = msg.get(A_XOR_PEER_ADDRESS)
        if ch_raw is None or peer_raw is None or len(ch_raw) < 4:
            self._send_error(msg, addr, transport, tcp_conn, 400, 'Bad Request')
            return
        channel = struct.unpack('!H', ch_raw[:2])[0]
        if channel < CHANNEL_RANGE[0] or channel > CHANNEL_RANGE[1]:
            self._send_error(msg, addr, transport, tcp_conn, 400, 'Bad channel number')
            return
        peer = parse_xor_address(peer_raw, msg.txid)
        if peer is None:
            self._send_error(msg, addr, transport, tcp_conn, 400, 'Bad peer address')
            return
        with self.lock:
            existing = alloc.channels.get(channel)
            if existing is not None and existing != peer:
                self._send_error(msg, addr, transport, tcp_conn, 400, 'Channel reused')
                return
            for ch, p in alloc.channels.items():
                if p == peer and ch != channel:
                    self._send_error(msg, addr, transport, tcp_conn, 400, 'Peer rebound')
                    return
            alloc.channels[channel] = peer
            alloc.add_permission(peer[0])
            self.relay_routes[peer] = alloc
        b = MessageBuilder(C_RESPONSE, M_CHANNEL_BIND, msg.txid)
        self._send_main(b.build(integrity_key=self.integrity_key),
                        addr, transport, tcp_conn)

    # ----- TURN Send indication (client -> peer) -----

    def _handle_send_indication(self, msg, addr, transport, tcp_conn):
        # Send indications carry no MESSAGE-INTEGRITY. Look up allocation
        # by the client's 5-tuple alone.
        with self.lock:
            alloc = self.allocations.get((transport, addr))
        if alloc is None:
            return
        peer_raw = msg.get(A_XOR_PEER_ADDRESS)
        data = msg.get(A_DATA)
        if peer_raw is None or data is None:
            return
        peer = parse_xor_address(peer_raw, msg.txid)
        if peer is None:
            return
        if not alloc.has_permission(peer[0]):
            return
        with self.lock:
            self.relay_routes[peer] = alloc
        try:
            self.relay_sock.sendto(data, peer)
        except OSError:
            pass

    # ----- ChannelData (client -> peer over channel) -----

    def _handle_channel_data(self, data, addr, transport, tcp_conn):
        if len(data) < 4:
            return
        channel, length = struct.unpack('!HH', data[:4])
        if length > len(data) - 4:
            return
        with self.lock:
            alloc = self.allocations.get((transport, addr))
        if alloc is None:
            return
        peer = alloc.channels.get(channel)
        if peer is None:
            return
        with self.lock:
            self.relay_routes[peer] = alloc
        try:
            self.relay_sock.sendto(data[4:4 + length], peer)
        except OSError:
            pass

    # ----- Inbound on shared relay socket (peer -> client) -----

    def _on_relay_inbound(self, sock):
        while True:
            try:
                data, peer = sock.recvfrom(65535)
            except BlockingIOError:
                return
            except OSError:
                return
            with self.lock:
                alloc = self.relay_routes.get(peer)
                if alloc is None:
                    # Permissions are by IP; channels are by (ip, port).
                    # Try IP-only fallback to find an allocation that
                    # has authorised this peer host.
                    for cand in self.allocations.values():
                        if cand.has_permission(peer[0]):
                            alloc = cand
                            break
            if alloc is None:
                continue
            self._deliver_inbound(alloc, peer, data)

    def _deliver_inbound(self, alloc, peer, data):
        # Prefer ChannelData framing if a channel is bound for this peer.
        channel = None
        for ch, p in alloc.channels.items():
            if p == peer:
                channel = ch
                break
        if channel is not None:
            payload = struct.pack('!HH', channel, len(data)) + data
            if alloc.transport == 'tcp':
                pad = pad4(4 + len(data))
                payload = payload + (b'\x00' * pad)
        else:
            b = MessageBuilder(C_INDICATION, M_DATA, secrets.token_bytes(12))
            b.add_xor_address(A_XOR_PEER_ADDRESS, peer[0], peer[1])
            b.add_attr(A_DATA, data)
            payload = b.build()
        if alloc.transport == 'udp':
            try:
                self.udp_main.sendto(payload, alloc.client_addr)
            except OSError:
                pass
        else:
            try:
                if alloc.tcp_conn is not None:
                    alloc.tcp_conn.sendall(payload)
            except OSError:
                with self.lock:
                    self._drop_allocation_locked(alloc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--listen-port', type=int,
                        default=int(os.getenv('LISTEN_PORT', '3478')))
    parser.add_argument('--relay-port', type=int,
                        default=int(os.getenv('RELAY_PORT', '50000')))
    parser.add_argument('--external-ip',
                        default=os.getenv('EXTERNAL_IP', '127.0.0.1'))
    parser.add_argument('--realm',
                        default=os.getenv('TURN_REALM', 'localhost'))
    parser.add_argument('--username',
                        default=os.getenv('TURN_USERNAME', 'username'))
    parser.add_argument('--password',
                        default=os.getenv('TURN_PASSWORD', 'password'))
    parser.add_argument('--log-level', default=os.getenv('LOG_LEVEL', 'INFO'))
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    # Resolve EXTERNAL_IP to IPv4 if a hostname was given.
    try:
        socket.inet_aton(args.external_ip)
        external_ip = args.external_ip
    except OSError:
        external_ip = socket.gethostbyname(args.external_ip)

    server = TurnServer(args.listen_port, args.relay_port, external_ip,
                        args.realm, args.username, args.password)
    server.setup()
    try:
        server.serve()
    except KeyboardInterrupt:
        LOG.info('shutting down')


if __name__ == '__main__':
    main()

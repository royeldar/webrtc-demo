package main

import (
	"fmt"
	"net"
	"sync"
	"time"
)

type peerKey struct {
	ip   string
	port int
}

func keyFromAddr(addr *net.UDPAddr) peerKey {
	return peerKey{ip: addr.IP.String(), port: addr.Port}
}

// SharedRelay owns a single UDP socket that all TURN allocations share as
// their relay endpoint. A read goroutine demultiplexes inbound packets to
// the allocation that previously sent traffic to the same peer 5-tuple.
type SharedRelay struct {
	conn       *net.UDPConn
	publicAddr *net.UDPAddr

	mu     sync.RWMutex
	routes map[peerKey]*allocConn
}

func NewSharedRelay(listenAddr, publicAddr *net.UDPAddr) (*SharedRelay, error) {
	conn, err := net.ListenUDP("udp4", listenAddr)
	if err != nil {
		return nil, err
	}
	sr := &SharedRelay{
		conn:       conn,
		publicAddr: publicAddr,
		routes:     map[peerKey]*allocConn{},
	}
	go sr.readLoop()
	return sr, nil
}

func (s *SharedRelay) readLoop() {
	buf := make([]byte, 65536)
	for {
		n, addr, err := s.conn.ReadFromUDP(buf)
		if err != nil {
			return
		}
		key := keyFromAddr(addr)
		s.mu.RLock()
		ac, ok := s.routes[key]
		s.mu.RUnlock()
		if !ok {
			continue
		}
		data := make([]byte, n)
		copy(data, buf[:n])
		select {
		case ac.inbound <- inboundPacket{data: data, src: cloneUDPAddr(addr)}:
		case <-ac.closed:
		default:
			// receive queue saturated — drop, same as a real socket would
		}
	}
}

func cloneUDPAddr(a *net.UDPAddr) *net.UDPAddr {
	ip := make(net.IP, len(a.IP))
	copy(ip, a.IP)
	return &net.UDPAddr{IP: ip, Port: a.Port, Zone: a.Zone}
}

func (s *SharedRelay) registerPeer(key peerKey, ac *allocConn) {
	s.mu.Lock()
	s.routes[key] = ac
	s.mu.Unlock()
}

func (s *SharedRelay) unregisterAlloc(ac *allocConn) {
	s.mu.Lock()
	for k, v := range s.routes {
		if v == ac {
			delete(s.routes, k)
		}
	}
	s.mu.Unlock()
}

type inboundPacket struct {
	data []byte
	src  *net.UDPAddr
}

// allocConn implements net.PacketConn as a per-allocation view onto the
// shared relay socket. ReadFrom pulls from a per-allocation channel that
// the SharedRelay read loop fills; WriteTo writes through the shared
// socket and registers the destination peer so its return packets are
// routed back to this allocation.
type allocConn struct {
	parent    *SharedRelay
	inbound   chan inboundPacket
	closed    chan struct{}
	closeOnce sync.Once
}

func newAllocConn(parent *SharedRelay) *allocConn {
	return &allocConn{
		parent:  parent,
		inbound: make(chan inboundPacket, 256),
		closed:  make(chan struct{}),
	}
}

func (a *allocConn) ReadFrom(p []byte) (int, net.Addr, error) {
	select {
	case pkt := <-a.inbound:
		n := copy(p, pkt.data)
		return n, pkt.src, nil
	case <-a.closed:
		return 0, nil, net.ErrClosed
	}
}

func (a *allocConn) WriteTo(p []byte, addr net.Addr) (int, error) {
	udp, ok := addr.(*net.UDPAddr)
	if !ok {
		resolved, err := net.ResolveUDPAddr("udp4", addr.String())
		if err != nil {
			return 0, err
		}
		udp = resolved
	}
	a.parent.registerPeer(keyFromAddr(udp), a)
	return a.parent.conn.WriteToUDP(p, udp)
}

func (a *allocConn) Close() error {
	a.closeOnce.Do(func() {
		close(a.closed)
		a.parent.unregisterAlloc(a)
	})
	return nil
}

func (a *allocConn) LocalAddr() net.Addr                { return a.parent.publicAddr }
func (a *allocConn) SetDeadline(t time.Time) error      { return nil }
func (a *allocConn) SetReadDeadline(t time.Time) error  { return nil }
func (a *allocConn) SetWriteDeadline(t time.Time) error { return nil }

// SharedRelayAddressGenerator hands out wrapped allocConns whose
// advertised relay address is the same EXTERNAL_IP:RELAY_PORT for every
// allocation. Browsers learn this address as their TURN relay candidate
// and send media to it; demultiplexing happens in SharedRelay.readLoop.
type SharedRelayAddressGenerator struct {
	Shared *SharedRelay
}

func (g *SharedRelayAddressGenerator) AllocatePacketConn(network string, _ int) (net.PacketConn, net.Addr, error) {
	if network != "udp4" && network != "udp" {
		return nil, nil, fmt.Errorf("unsupported relay network %q", network)
	}
	return newAllocConn(g.Shared), g.Shared.publicAddr, nil
}

func (g *SharedRelayAddressGenerator) AllocateConn(network string, _ int) (net.Conn, net.Addr, error) {
	return nil, nil, fmt.Errorf("TCP relay not implemented")
}

func (g *SharedRelayAddressGenerator) Validate() error {
	if g.Shared == nil || g.Shared.conn == nil {
		return fmt.Errorf("shared relay not initialised")
	}
	return nil
}

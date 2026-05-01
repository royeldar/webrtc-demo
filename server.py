#!/usr/bin/env python3

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from http import HTTPStatus
from threading import Lock
from queue import Queue, Empty
from io import BytesIO
from collections import defaultdict
import argparse
import socket
import ssl
import os
import secrets

usernames = {}
tokens = {}
lock = Lock()
poison = object()


class Username:
    def __init__(self, password, secret):
        self.password = password
        self.secret = secret
        self.messages = defaultdict(Queue)
        self.tokens = {}


class Token:
    def __init__(self, receiver, sender):
        self.receiver = receiver
        self.sender = sender


class MyHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='static', **kwargs)

    def do_GET(self):
        path = self.path
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        if path in ['/', '/index.html', '/styles.css', '/script.js']:
            super().do_GET()
        elif path.startswith('/api/receive/'):
            path = path.removeprefix('/api/receive/')
            token = path.encode()
            error = False
            with lock:
                if token not in tokens:
                    error = True
                else:
                    receiver = tokens[token].receiver
                    sender = tokens[token].sender
                    queue = usernames[receiver].messages[sender]
            if error:
                self.send_error(HTTPStatus.NOT_FOUND, 'Token doesn\'t exist')
            else:
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'keep-alive')
                self.end_headers()
                while True:
                    try:
                        data = queue.get(timeout=30)
                    except Empty:
                        data = None
                    if data is poison:
                        break
                    try:
                        if data is not None:
                            data = data.strip(b'\n')
                            data = data.replace(b'\n', b'\ndata: ')
                            data = b'data: ' + data + b'\n\n'
                            self.wfile.write(data)
                        else:
                            self.wfile.write(b': keep-alive\n\n')
                        self.wfile.flush()
                    except (ConnectionResetError, BrokenPipeError):
                        break
        else:
            self.send_error(HTTPStatus.NOT_FOUND, 'File not found')

    def do_POST(self):
        content_length = self.headers.get('content-length')
        if not content_length:
            self.send_error(HTTPStatus.LENGTH_REQUIRED)
            return

        length = int(content_length)
        if length > 65536:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return

        if self.path == '/api/register':
            try:
                username, password, secret = self.rfile.read(length).split(b'\n')
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST, 'Request is invalid')
                return
            username = username.strip()
            password = password.strip()
            secret = secret.strip()
            error = False
            with lock:
                if username in usernames:
                    error = True
                else:
                    usernames[username] = Username(password=password, secret=secret)
            if error:
                self.send_error(HTTPStatus.CONFLICT, 'Username already exists')
            else:
                self.send_response(HTTPStatus.OK)
                self.end_headers()
        elif self.path == '/api/unregister':
            try:
                username, password = self.rfile.read(length).split(b'\n')
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST, 'Request is invalid')
                return
            username = username.strip()
            password = password.strip()
            error = False
            with lock:
                if username not in usernames:
                    error = True
                elif usernames[username].password != password:
                    error = True
                else:
                    for token in usernames[username].tokens.values():
                        del tokens[token]
                    del usernames[username]
                    for username2 in usernames:
                        if username in usernames[username2].messages:
                            usernames[username2].messages[username].put(poison)
                            del usernames[username2].messages[username]
                        if username in usernames[username2].tokens:
                            token = usernames[username2].tokens[username]
                            del usernames[username2].tokens[username]
                            del tokens[token]
            if error:
                self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist or password is incorrect')
            else:
                self.send_response(HTTPStatus.OK)
                self.end_headers()
        elif self.path == '/api/token/new':
            try:
                receiver, receiver_password, sender = self.rfile.read(length).split(b'\n')
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST, 'Request is invalid')
                return
            receiver = receiver.strip()
            receiver_password = receiver_password.strip()
            sender = sender.strip()
            error = False
            with lock:
                if receiver not in usernames or usernames[receiver].password != receiver_password:
                    error = True
                elif sender not in usernames:
                    error = True
                else:
                    token = secrets.token_urlsafe().encode()
                    assert token not in tokens
                    old_token = usernames[receiver].tokens.get(sender)
                    if old_token is not None:
                        del tokens[old_token]
                        usernames[receiver].messages[sender].put(poison)
                        usernames[receiver].messages[sender] = Queue()
                    usernames[receiver].tokens[sender] = token
                    tokens[token] = Token(receiver, sender)
            if error:
                self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist or password is incorrect')
            else:
                f = BytesIO()
                f.write(token)
                f.seek(0)
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-Length', str(len(token)))
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.copyfile(f, self.wfile)
                f.close()
        elif self.path == '/api/token/delete':
            token = self.rfile.read(length)
            error = False
            if token not in tokens:
                error = True
            else:
                with lock:
                    receiver = tokens[token].receiver
                    sender = tokens[token].sender
                    del usernames[receiver].tokens[sender]
                    del tokens[token]
                    usernames[receiver].messages[sender].put(poison)
                    usernames[receiver].messages[sender] = Queue()
            if error:
                self.send_error(HTTPStatus.NOT_FOUND, 'Token doesn\'t exist')
            else:
                self.send_response(HTTPStatus.OK)
                self.end_headers()
        elif self.path == '/api/send':
            try:
                sender, sender_password, receiver, receiver_secret, data = self.rfile.read(length).split(b'\n', 4)
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST, 'Request is invalid')
                return
            sender = sender.strip()
            sender_password = sender_password.strip()
            receiver = receiver.strip()
            receiver_secret = receiver_secret.strip()
            data = data.strip()
            error = False
            with lock:
                if sender not in usernames or usernames[sender].password != sender_password:
                    error = True
                elif receiver not in usernames or usernames[receiver].secret != receiver_secret:
                    error = True
                else:
                    usernames[receiver].messages[sender].put(data)
            if error:
                self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist, password is incorrect or secret is incorrect')
            else:
                self.send_response(HTTPStatus.OK)
                self.end_headers()

    def log_message(self, format, *args):
        pass

class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()

    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(60)
        return sock, addr


def run(port, certfile, keyfile, password):
    server_address = ('::', port)
    httpd = DualStackServer(server_address, MyHTTPRequestHandler)
    if certfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=certfile, keyfile=keyfile, password=password)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nKeyboard interrupt received, exiting.')
    finally:
        httpd.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--certfile', default=None)
    parser.add_argument('--keyfile', default=None)
    args = parser.parse_args()
    password = os.getenv('SSL_PASSWORD')
    run(port=args.port, certfile=args.certfile, keyfile=args.keyfile, password=password)


if __name__ == '__main__':
    main()

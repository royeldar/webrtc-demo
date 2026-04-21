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

usernames = {}
lock = Lock()


class Username:
    def __init__(self, password, secret):
        self.password = password
        self.secret = secret
        self.messages = defaultdict(Queue)

class MyHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='static', **kwargs)

    def do_GET(self):
        path = self.path
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        if path in ['/', '/index.html', '/styles.css', '/script.js']:
            super().do_GET()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, 'File not found')

    def do_POST(self):
        length = int(self.headers.get('content-length'))
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
                    del usernames[username]
                    for username2 in usernames:
                        if username in usernames[username2].messages:
                            del usernames[username2].messages[username]
            if error:
                self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist or password is incorrect')
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
        elif self.path == '/api/receive':
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
                else:
                    try:
                       data = usernames[receiver].messages[sender].get_nowait()
                    except Empty:
                        data = None
            if error:
                self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist or password is incorrect')
            elif data is None:
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
            else:
                f = BytesIO()
                f.write(data)
                f.seek(0)
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.copyfile(f, self.wfile)
                f.close()

    def log_message(self, format, *args):
        pass

class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def run(port, certfile, keyfile, password):
    server_address = ('::', port)
    httpd = DualStackServer(server_address, MyHTTPRequestHandler)
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
    parser.add_argument('--port', type=int, default=8443)
    parser.add_argument('--certfile', default='cert.pem')
    parser.add_argument('--keyfile', default='key.pem')
    args = parser.parse_args()
    password = os.getenv('SSL_PASSWORD')
    run(port=args.port, certfile=args.certfile, keyfile=args.keyfile, password=password)


if __name__ == '__main__':
    main()

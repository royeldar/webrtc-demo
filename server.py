#!/usr/bin/env python3

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from http import HTTPStatus
from threading import Lock
from queue import Queue, Empty
from io import BytesIO
from collections import defaultdict
import argparse

usernames = {}
lock = Lock()

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
        if self.path == '/api/register':
            length = int(self.headers.get('content-length'))
            username = self.rfile.read(length).strip()
            if b'\n' in username:
                self.send_error(HTTPStatus.BAD_REQUEST, 'Username is invalid')
                return
            error = False
            with lock:
                if username in usernames:
                    error = True
                else:
                    usernames[username] = defaultdict(Queue)
            if error:
                self.send_error(HTTPStatus.CONFLICT, 'Username already exists')
            else:
                self.send_response(HTTPStatus.OK)
                self.end_headers()
        elif self.path == '/api/unregister':
            length = int(self.headers.get('content-length'))
            username = self.rfile.read(length).strip()
            error = False
            with lock:
                if username not in usernames:
                    error = True
                else:
                    del usernames[username]
                    for username2 in usernames:
                        if username in usernames[username2]:
                            del usernames[username2][username]
            if error:
                self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist')
            else:
                self.send_response(HTTPStatus.OK)
                self.end_headers()
        elif self.path == '/api/send':
            length = int(self.headers.get('content-length'))
            sender, receiver, data = self.rfile.read(length).split(b'\n', 2)
            sender = sender.strip()
            receiver = receiver.strip()
            data = data.strip()
            error = False
            with lock:
                if receiver not in usernames:
                    error = True
                else:
                    usernames[receiver][sender].put(data)
            if error:
                self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist')
            else:
                self.send_response(HTTPStatus.OK)
                self.end_headers()
        elif self.path == '/api/receive':
            length = int(self.headers.get('content-length'))
            receiver, sender = self.rfile.read(length).split(b'\n')
            receiver = receiver.strip()
            sender = sender.strip()
            error = False
            with lock:
                if receiver not in usernames:
                    error = True
                else:
                    try:
                       data = usernames[receiver][sender].get_nowait()
                    except Empty:
                        data = None
            if error:
                self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist')
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


def run(address, port, server_class=ThreadingHTTPServer, handler_class=MyHTTPRequestHandler):
    server_address = (address, port)
    # TODO listen on ipv6 as well
    httpd = server_class(server_address, handler_class)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nKeyboard interrupt received, exiting.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--address', default='localhost')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    run(address=args.address, port=args.port)


if __name__ == '__main__':
    main()

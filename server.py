#!/usr/bin/env python3

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from http import HTTPStatus
from threading import Lock
from queue import Queue, Empty
from io import BytesIO

ADDRESS = 'localhost'
PORT = 80

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
            with lock:
                if username in usernames:
                    self.send_error(HTTPStatus.CONFLICT, 'Username already exists')
                    return
                usernames[username] = Queue()
            self.send_response(HTTPStatus.OK)
            self.end_headers()
        elif self.path == '/api/unregister':
            length = int(self.headers.get('content-length'))
            username = self.rfile.read(length).strip()
            with lock:
                if username not in usernames:
                    self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist')
                    return
                del usernames[username]
            self.send_response(HTTPStatus.OK)
            self.end_headers()
        elif self.path == '/api/send':
            length = int(self.headers.get('content-length'))
            username, data = self.rfile.read(length).split(b'\n', 1)
            username = username.strip()
            data = data.strip()
            with lock:
                if username not in usernames:
                    self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist')
                    return
                usernames[username].put(data)
            self.send_response(HTTPStatus.OK)
            self.end_headers()
        elif self.path == '/api/receive':
            length = int(self.headers.get('content-length'))
            username = self.rfile.read(length).strip()
            with lock:
                if username not in usernames:
                    self.send_error(HTTPStatus.NOT_FOUND, 'Username doesn\'t exist')
                    return
                try:
                    data = usernames[username].get_nowait()
                    f = BytesIO()
                    f.write(data)
                    f.seek(0)
                    self.send_response(HTTPStatus.OK)
                    self.send_header('Content-Length', str(len(data)))
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.end_headers()
                    self.copyfile(f, self.wfile)
                    f.close()
                except Empty:
                    self.send_response(HTTPStatus.NO_CONTENT)
                    self.end_headers()

    def log_message(self, format, *args):
        pass


def run(server_class=ThreadingHTTPServer, handler_class=MyHTTPRequestHandler):
    server_address = (ADDRESS, PORT)
    # TODO listen on ipv6 as well
    httpd = server_class(server_address, handler_class)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nKeyboard interrupt received, exiting.')


if __name__ == '__main__':
    run()

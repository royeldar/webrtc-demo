#!/usr/bin/env python3

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from http import HTTPStatus

ADDRESS = 'localhost'
PORT = 80

class MyHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='static', **kwargs)

    def do_GET(self):
        if self.path in ['/', '/index.html']:
            super().do_GET()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, 'File not found')


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

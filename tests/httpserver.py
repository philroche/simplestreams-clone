#!/usr/bin/env python
import os
import sys
if sys.version_info.major == 2:
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from BaseHTTPServer import HTTPServer
else:
    from http.server import SimpleHTTPRequestHandler
    from http.server import HTTPServer


class LoggingHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        """
        Log an accepted request along with user-agent string.
        """

        user_agent = self.headers.get("user-agent")
        self.log_message('"%s" %s %s (%s)',
                         self.requestline, str(code), str(size), user_agent)


def run(address, port,
        HandlerClass=LoggingHTTPRequestHandler, ServerClass=HTTPServer):
    try:
        server = ServerClass((address, port), HandlerClass)
        address, port = server.socket.getsockname()
        sys.stderr.write("Serving HTTP: %s %s %s\n" %
                         (address, port, os.getcwd()))
        server.serve_forever()
    except KeyboardInterrupt:
        server.socket.close()


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3:
        # 2 args: address and port
        address = sys.argv[1]
        port = int(sys.argv[2])
    elif len(sys.argv) == 2:
        # 1 arg: port
        address = '0.0.0.0'
        port = int(sys.argv[1])
    elif len(sys.argv) == 1:
        # no args random port (port=0)
        address = '0.0.0.0'
        port = 0
    else:
        sys.stderr.write("Expect [address] [port]\n")
        sys.exit(1)
    run(address=address, port=port)

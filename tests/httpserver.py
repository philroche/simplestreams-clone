#!/usr/bin/env python
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
        sys.stderr.write("Serving HTTP on %s:%s\n" % (address, port))
        server.serve_forever()
    except KeyboardInterrupt:
        server.socket.close()


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3:
        address = sys.argv[1]
        port = int(sys.argv[2])
    elif len(sys.argv) == 2:
        address = '0.0.0.0'
        port = int(sys.argv[1])
    else:
        sys.stderr.write("Expect [address] port\n")
        sys.exit(1)
    run(address=address, port=port)

import SimpleHTTPServer


class LoggingHTTPRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        """
        Log an accepted request along with user-agent string.
        """

        user_agent = self.headers.get("user-agent")
        self.log_message('"%s" %s %s (%s)',
                         self.requestline, str(code), str(size), user_agent)


def run(HandlerClass=LoggingHTTPRequestHandler,
        ServerClass=SimpleHTTPServer.BaseHTTPServer):
    ServerClass.test(HandlerClass, ServerClass.HTTPServer)


if __name__ == '__main__':
    run()

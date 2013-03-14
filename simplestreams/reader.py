class Reader(object):
    def __init__(self, reader, url):
        self.reader = reader
        self.url = url

    def read(self, size=-1):
        return self.reader.read(size)

    def __enter__(self):
        return self

    def __exit__(self, type, value, trace):
        self.reader.close()

    def close(self):
        self.reader.close()


class RequestsUrlReader(object):
    def __init__(self, url, buflen=None):
        self.url = url
        self.req = requests.get(url, stream=True)
        self.r_iter = None
        if buflen is None:
            buflen = 1024 * 1024
        self.buflen = buflen
        self.leftover = None
        self.consumed = False

        if self.req.status_code == requests.codes.NOT_FOUND:
            myerr = IOError("Unable to open %s" % url)
            myerr.errno = errno.ENOENT
            raise myerr

        ce = self.req.headers.get('content-encoding', '').lower()
        if 'gzip' in ce or 'deflate' in ce:
            self._read = self.read_compressed
        else:
            self._read = self.read_raw

    def read(self, size=-1):
        if size < 0:
            size = None
        return self._read(size)

    def read_compressed(self, size=None):
        if not self.r_iter:
            self.r_iter = self.req.iter_content(self.buflen)

        if self.consumed:
            return bytes()

        ret = bytes()

        if self.leftover is not None:
            if len(self.leftover) > size:
                ret = self.leftover[0:size]
                self.leftover = self.leftover[size:]
                return ret
            ret = self.leftover
            self.leftover = None

        size_end = (size is not None and size >= 0)

        while True:
            try:
                ret += self.r_iter.next()
                if not size_end:
                    next
                if len(ret) >= size:
                    self.leftover = ret[size:]
                    return ret[0:size]
            except StopIteration as e:
                self.consumed = True
                return ret

    def read_raw(self, size=None):
        return self.req.raw.read(size)

    def close(self):
        self.req.close()

# vi: ts=4 expandtab

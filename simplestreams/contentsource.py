import errno
import os
import StringIO
import urlparse

try:
    import requests
    from distutils.version import LooseVersion
    import pkg_resources
    _REQ = pkg_resources.get_distribution('requests')
    _REQ_VER = LooseVersion(_REQ.version)  # pylint: disable=E1103
    if _REQ_VER < LooseVersion('1.1'):
        raise Exception("Couldn't use requests")
    URL_READER_CLASSNAME = "RequestsUrlReader"
except:
    import urllib2
    URL_READER_CLASSNAME = "Urllib2UrlReader"


class ContentSource(object):
    url = None

    def open(self):
        # open can be explicitly called to 'open', but might be implicitly
        # called from read()
        pass

    def read(self, size=-1):
        raise NotImplementedError()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, etype, value, trace):
        self.close()

    def close(self):
        raise NotImplementedError()


class UrlContentSource(ContentSource):
    fd = None

    def __init__(self, url, mirrors=None):
        if mirrors is None:
            mirrors = []
        self.mirrors = mirrors
        self.input_url = url
        self.url = url

    def _urlinfo(self, url):
        parsed = urlparse.urlparse(url)
        if not parsed.scheme:
            if url.startswith("/"):
                url = "file://%s" % url
            else:
                url = "file://%s/%s" % (os.getcwd(), url)
            parsed = urlparse.urlparse(url)

        if parsed.scheme == "file":
            return (url, open, (parsed.path,))
        else:
            return (url, URL_READER, (url,))

    def _open(self):
        for url in [self.input_url] + self.mirrors:
            try:
                (normurl, opener, oargs) = self._urlinfo(url)
                self.url = normurl
                return opener(*oargs)
            except IOError as e:
                if e.errno != errno.ENOENT:
                    raise
                continue
        myerr = IOError("Unable to open %s. mirrors=%s" %
                        (self.input_url, self.mirrors))
        myerr.errno = errno.ENOENT
        raise myerr

    def open(self):
        self.fd = self._open()
        self.read = self._read

    def read(self, size=-1):
        if self.fd is None:
            self.open()

        return self._read(size)

    def _read(self, size=-1):
        return self.fd.read(size)

    def close(self):
        if self.fd:
            self.fd.close()
            self.fd = None
            self.open = self._open


class FdContentSource(ContentSource):
    def __init__(self, fd, url=None):
        self.fd = fd
        self.url = url

    def read(self, size=-1):
        return self.fd.read(size)

    def close(self):
        self.fd.close()


class MemoryContentSource(FdContentSource):
    def __init__(self, url=None, content=""):
        fd = StringIO.StringIO(content)
        if url is None:
            url = "MemoryContentSource://undefined"
        super(MemoryContentSource, self).__init__(fd=fd, url=url)


class UrlReader(object):
    def __init__(self, url):
        raise NotImplementedError()

    def read(self, size=-1):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()


class Urllib2UrlReader(UrlReader):
    def __init__(self, url):
	self.url = url
        try:
            self.req = urllib2.urlopen(url)
        except urllib2.HTTPError as e:
            if e.code == 404:
                myerr = IOError("Unable to open %s" % url)
                myerr.errno = errno.ENOENT
                raise myerr
            raise e
 
    def read(self, size=-1):
        return self.req.read(size)

    def close(self):
        return self.req.close()


class RequestsUrlReader(UrlReader):
    # This provides a url reader that supports deflate/gzip encoding
    # but still implements 'read'.
    # r = RequestsUrlReader(http://example.com)
    # r.read(10)
    # r.close()
    def __init__(self, url, buflen=None):
        self.url = url
        self.req = requests.get(url, stream=True)
        self.r_iter = None
        if buflen is None:
            buflen = 1024 * 1024
        self.buflen = buflen
        self.leftover = bytes()
        self.consumed = False

        if (self.req.status_code ==
                requests.codes.NOT_FOUND):  # pylint: disable=E1101
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

        if (size is None or size < 0):
            # read everything
            ret = self.leftover
            self.leftover = bytes()
            for buf in self.r_iter:
                ret += buf
            self.consumed = True
            return ret

        ret = bytes()

        if self.leftover:
            if len(self.leftover) > size:
                ret = self.leftover[0:size]
                self.leftover = self.leftover[size:]
                return ret
            ret = self.leftover
            self.leftover = bytes()

        while True:
            try:
                ret += self.r_iter.next()
                if len(ret) >= size:
                    self.leftover = ret[size:]
                    ret = ret[0:size]
                    break
            except StopIteration:
                self.consumed = True
                break
        return ret

    def read_raw(self, size=None):
        return self.req.raw.read(size)

    def close(self):
        self.req.close()


if URL_READER_CLASSNAME == "RequestsUrlReader":
    URL_READER = RequestsUrlReader
elif URL_READER_CLASSNAME == "Urllib2UrlReader":
    URL_READER = Urllib2UrlReader
else:
    raise Exception("Unknown URL_READER_CLASSNAME: %s" % URL_READER_CLASSNAME)

# vi: ts=4 expandtab

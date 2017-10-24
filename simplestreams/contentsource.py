#   Copyright (C) 2013 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
#
#   Simplestreams is free software: you can redistribute it and/or modify it
#   under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Simplestreams is distributed in the hope that it will be useful, but
#   WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
#   or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public
#   License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Simplestreams.  If not, see <http://www.gnu.org/licenses/>.

import errno
import io
import os
import sys

from . import checksum_util

if sys.version_info > (3, 0):
    import urllib.parse as urlparse
    import urllib.request as urllib_request
    import urllib.error as urllib_error
else:
    import urlparse
    import urllib2 as urllib_request
    urllib_error = urllib_request

READ_BUFFER_SIZE = 1024 * 10

try:
    # We try to use requests because we can do gzip encoding with it.
    # however requests < 1.1 didn't have 'stream' argument to 'get'
    # making it completely unsuitable for downloading large files.
    import requests
    from distutils.version import LooseVersion
    import pkg_resources
    _REQ = pkg_resources.get_distribution('requests')
    _REQ_VER = LooseVersion(_REQ.version)
    if _REQ_VER < LooseVersion('1.1'):
        raise ImportError("Requests version < 1.1, not suitable for usage.")
    URL_READER_CLASSNAME = "RequestsUrlReader"
except ImportError:
    URL_READER_CLASSNAME = "Urllib2UrlReader"
    requests = None


class ContentSource(object):
    url = None

    def open(self):
        # open can be explicitly called to 'open', but might be implicitly
        # called from read()
        pass

    def read(self, size=-1):
        raise NotImplementedError()

    def set_start_pos(self, offset):
        """ Implemented if the ContentSource supports seeking within content.
        Used to resume failed transfers. """

        class SetStartPosNotImplementedError(NotImplementedError):
            pass

        raise SetStartPosNotImplementedError()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, etype, value, trace):
        self.close()

    def close(self):
        raise NotImplementedError()


class UrlContentSource(ContentSource):
    fd = None

    def __init__(self, url, mirrors=None, url_reader=None):
        if mirrors is None:
            mirrors = []
        self.mirrors = mirrors
        self.input_url = url
        self.url = url
        self.offset = None
        self.fd = None
        if url_reader is None:
            self.url_reader = URL_READER
        else:
            self.url_reader = url_reader

    def _urlinfo(self, url):
        parsed = urlparse.urlparse(url)
        if not parsed.scheme:
            if url.startswith("/"):
                url = "file://%s" % url
            else:
                url = "file://%s/%s" % (os.getcwd(), url)
            parsed = urlparse.urlparse(url)

        if parsed.scheme == "file":
            return (url, FileReader, (parsed.path,))
        else:
            return (url, self.url_reader, (url,))

    def _open(self):
        for url in [self.input_url] + self.mirrors:
            try:
                (normurl, opener, oargs) = self._urlinfo(url)
                self.url = normurl
                return opener(*oargs, offset=self.offset)
            except IOError as e:
                if e.errno != errno.ENOENT:
                    raise
                continue
        myerr = IOError("Unable to open %s. mirrors=%s" %
                        (self.input_url, self.mirrors))
        myerr.errno = errno.ENOENT
        raise myerr

    def open(self):
        if self.fd is None:
            self.fd = self._open()

    def read(self, size=-1):
        if self.fd is None:
            self.open()
        return self.fd.read(size)

    def set_start_pos(self, offset):
        if self.fd is not None:
            raise Exception("can't set start pos after open()")
        self.offset = offset

    def close(self):
        if self.fd:
            self.fd.close()
            self.fd = None


class FdContentSource(ContentSource):
    def __init__(self, fd, url=None):
        self.fd = fd
        self.url = url

    def read(self, size=-1):
        return self.fd.read(size)

    def close(self):
        self.fd.close()


class IteratorContentSource(ContentSource):
    def __init__(self, itgen, url=None):
        self.itgen = itgen
        self.url = url
        self.r_iter = None
        self.leftover = bytes()
        self.consumed = False

    def open(self):
        if self.r_iter:
            return

        try:
            self.r_iter = self.itgen()
        except Exception as exc:
            if self.is_enoent(exc):
                enoent = IOError(exc)
                enoent.errno = errno.ENOENT
                raise enoent
            raise exc

    def is_enoent(self, exc):
        return (isinstance(exc, IOError) and exc.errno == errno.ENOENT)

    def read(self, size=None):
        self.open()

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
                ret += next(self.r_iter)
                if len(ret) >= size:
                    self.leftover = ret[size:]
                    ret = ret[0:size]
                    break
            except StopIteration:
                self.consumed = True
                break
        return ret

    def close(self):
        pass


class MemoryContentSource(FdContentSource):
    def __init__(self, url=None, content=""):
        if isinstance(content, str):
            content = content.encode('utf-8')
        fd = io.BytesIO(content)
        if url is None:
            url = "MemoryContentSource://undefined"
        super(MemoryContentSource, self).__init__(fd=fd, url=url)


class ChecksummingContentSource(ContentSource):
    def __init__(self, csrc, checksums, size=None):
        self.cs = csrc
        self.bytes_read = 0
        self.checksummer = None
        self.size = size

        try:
            csummer = checksum_util.SafeCheckSummer(checksums)
        except ValueError as e:
            raise checksum_util.invalid_checksum_for_reader(self, msg=str(e))

        self._set_checksummer(csummer)

        try:
            self.size = int(size)
        except TypeError:
            self.size = size
            raise checksum_util.invalid_checksum_for_reader(self)

    def resume(self, offset, checksummer):
        self.cs.set_start_pos(offset)
        self._set_checksummer(checksummer)
        self.bytes_read = offset

    @property
    def algorithm(self):
        return self.checksummer.algorithm

    def _set_checksummer(self, checksummer):
        if checksummer.algorithm not in checksum_util.CHECKSUMS:
            raise ValueError("algorithm %s is not valid (%s)" %
                             (checksummer.algorithm, checksum_util.CHECKSUMS))
        self.checksummer = checksummer

    def check(self):
        return self.bytes_read == self.size and self.checksummer.check()

    def read(self, size=-1):
        buf = self.cs.read(size)
        buflen = len(buf)
        self.checksummer.update(buf)
        self.bytes_read += buflen

        # read size was different size than expected.
        # if its not the end, something wrong
        if buflen != size and self.size != self.bytes_read:
            raise checksum_util.invalid_checksum_for_reader(self)

        if self.bytes_read == self.size and not self.check():
            raise checksum_util.invalid_checksum_for_reader(self)
        return buf

    def open(self):
        return self.cs.open()

    def close(self):
        return self.cs.close()

    @property
    def url(self):
        return self.cs.url


class UrlReader(object):
    def read(self, size=-1):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()


class FileReader(UrlReader):
    def __init__(self, path, offset=None, user_agent=None):
        if path.startswith("file://"):
            path = path[7:]
        self.fd = open(path, "rb")
        if offset is not None:
            self.fd.seek(offset)

    def read(self, size=-1):
        return _read_fd(self.fd, size)

    def close(self):
        return self.fd.close()


class Urllib2UrlReader(UrlReader):
    def __init__(self, url, offset=None, user_agent=None):
        (url, username, password) = parse_url_auth(url)
        self.url = url
        if username is None:
            opener = urllib_request.urlopen
        else:
            mgr = urllib_request.HTTPPasswordMgrWithDefaultRealm()
            mgr.add_password(None, url, username, password)
            handler = urllib_request.HTTPBasicAuthHandler(mgr)
            opener = urllib_request.build_opener(handler).open

        try:
            req = urllib_request.Request(url)
            if user_agent is not None:
                req.add_header('User-Agent', user_agent)
            if offset is not None:
                req.add_header('Range', 'bytes=%d-' % offset)
            self.req = opener(req)
        except urllib_error.HTTPError as e:
            if e.code == 404:
                myerr = IOError("Unable to open %s" % url)
                myerr.errno = errno.ENOENT
                raise myerr
            raise e

    def read(self, size=-1):
        return _read_fd(self.req, size)

    def close(self):
        return self.req.close()


class RequestsUrlReader(UrlReader):
    # This provides a url reader that supports deflate/gzip encoding
    # but still implements 'read'.
    # r = RequestsUrlReader(http://example.com)
    # r.read(10)
    # r.close()
    def __init__(self, url, buflen=None, offset=None, user_agent=None):
        if requests is None:
            raise ImportError("Attempt to use RequestsUrlReader "
                              "without suitable requests library.")
        self.url = url
        (url, user, password) = parse_url_auth(url)
        if user is None:
            auth = None
        else:
            auth = (user, password)

        headers = {}
        if user_agent is not None:
            headers['User-Agent'] = user_agent
        if offset is not None:
            headers['Range'] = 'bytes=%d-' % offset
        if headers == {}:
            headers = None

        self.req = requests.get(url, stream=True, auth=auth, headers=headers)
        self.r_iter = None
        if buflen is None:
            buflen = READ_BUFFER_SIZE
        self.buflen = buflen
        self.leftover = bytes()
        self.consumed = False

        if (self.req.status_code == requests.codes.NOT_FOUND):
            myerr = IOError("Unable to open %s" % url)
            myerr.errno = errno.ENOENT
            raise myerr

        ce = self.req.headers.get('content-encoding', '').lower()
        if 'gzip' in ce or 'deflate' in ce:
            self._read = self.read_compressed
        else:
            self._read = self.read_raw

    def read(self, size=-1):
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
                ret += next(self.r_iter)
                if len(ret) >= size:
                    self.leftover = ret[size:]
                    ret = ret[0:size]
                    break
            except StopIteration:
                self.consumed = True
                break
        return ret

    def read_raw(self, size=-1):
        return _read_fd(self.req.raw, size)

    def close(self):
        self.req.close()


def parse_url_auth(url):
    parsed = urlparse.urlparse(url)
    authtok = "%s:%s@" % (parsed.username, parsed.password)
    if parsed.netloc.startswith(authtok):
        url = url.replace(authtok, "", 1)
    return (url, parsed.username, parsed.password)


def _read_fd(fd, size=-1):
    # normalize calling of fd.read()
    # python3 generally wants fd.read(size=None)
    # python2 generally wants fd.read(size=-1)
    if size is None or size < 0:
        return fd.read()
    return fd.read(size)


if URL_READER_CLASSNAME == "RequestsUrlReader":
    URL_READER = RequestsUrlReader
elif URL_READER_CLASSNAME == "Urllib2UrlReader":
    URL_READER = Urllib2UrlReader
else:
    raise Exception("Unknown URL_READER_CLASSNAME: %s" % URL_READER_CLASSNAME)

# vi: ts=4 expandtab

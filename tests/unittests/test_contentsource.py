import os
import shutil
import sys
import tempfile

from os.path import join, dirname
from simplestreams import objectstores
from simplestreams import contentsource
from subprocess import Popen, PIPE, STDOUT
from unittest import TestCase, skipIf
from nose.tools import raises


class RandomPortServer(object):
    def __init__(self, path):
        self.path = path
        self.process = None
        self.port = None
        self.process = None

    def serve(self):
        if self.port and self.process:
            return
        testserver_path = join(
            dirname(__file__), "..", "..", "tests", "httpserver.py")
        pre = b'Serving HTTP:'

        cmd = [sys.executable, '-u', testserver_path, "0"]
        p = Popen(cmd, cwd=self.path, stdout=PIPE, stderr=STDOUT)
        line = p.stdout.readline()  # pylint: disable=E1101
        if line.startswith(pre):
            data = line[len(pre):].strip()
            addr, port_str, cwd = data.decode().split(" ", 2)
            self.port = int(port_str)
            self.addr = addr
            self.process = p
            # print("Running server on %s" % port_str)
            return
        else:
            p.kill()
            raise RuntimeError(
                "Failed to start server in %s with %s. pid=%s. got: %s" %
                (self.path, cmd, self.process, line))

    def read_output(self):
        return str(self.process.stdout.readline())

    def unserve(self):
        if self.process:
            self.process.kill()  # pylint: disable=E1101
        self.process = None
        self.port = None

    def __enter__(self):
        self.serve()
        return self

    def __exit__(self, _type, value, tb):
        self.unserve()

    def __repr__(self):
        pid = None
        if self.process:
            pid = self.process.pid

        return("RandomPortServer(port=%s, addr=%s, process=%s, path=%s)" %
               (self.port, self.addr, pid, self.path))

    def url_for(self, fpath=""):
        if self.port is None:
            raise ValueError("No port available")
        return 'http://127.0.0.1:%d/' % self.port + fpath


class BaseDirUsingTestCase(TestCase):
    http = False
    server = None
    tmpd = None

    @classmethod
    def setUpClass(cls):
        cls.tmpd = os.path.abspath(tempfile.mkdtemp(prefix="ss-unit."))
        if cls.http:
            cls.server = RandomPortServer(cls.tmpd)
            cls.server.serve()
            print(cls.server)

    @classmethod
    def tearDownClass(cls):
        if cls.http:
            cls.server.unserve()
            shutil.rmtree(cls.tmpd)

    def mkdtemp(self):
        return tempfile.mkdtemp(dir=self.tmpd)

    def setUp(self):
        # each individual test gets its own dir that can be served.
        self.test_d = self.mkdtemp()

    def getcs(self, path, url_reader=None, rel=None):
        return contentsource.UrlContentSource(
            self.url_for(path, rel=rel), url_reader=url_reader)

    def path_for(self, fpath, rel=None):
        # return full path to fpath.
        #  if fpath is absolute path, must be under self.tmpd
        #  if not absolute, it is relative to 'rel' (default self.test_d)
        if fpath is None:
            fpath = ""

        if os.path.isabs(fpath):
            fullpath = os.path.abspath(fpath)
        else:
            if rel is None:
                rel = self.test_d
            else:
                rel = self.tmpd
            fullpath = os.path.abspath(os.path.sep.join([rel, fpath]))

        if not fullpath.startswith(self.tmpd + os.path.sep):
            raise ValueError(
                "%s is not a valid path.  Not under tmpdir: %s" %
                (fpath, self.tmpd))

        return fullpath

    def furl_for(self, fpath=None, rel=None):
        return "file://" + self.path_for(fpath=fpath, rel=rel)

    def url_for(self, fpath=None, rel=None):
        # return a url for fpath.
        if not self.server:
            raise ValueError("No server available, but proto == http")
        return self.server.url_for(
            self.path_for(fpath=fpath, rel=rel)[len(self.tmpd)+1:])


class TestUrlContentSource(BaseDirUsingTestCase):
    http = True
    fpath = 'foo'
    fdata = b'hello world\n'

    def setUp(self):
        super(TestUrlContentSource, self).setUp()
        with open(join(self.test_d, self.fpath), 'wb') as f:
            f.write(self.fdata)

    def test_default_url_read_handles_None(self):
        scs = contentsource.UrlContentSource(self.url_for(self.fpath))
        data = scs.read(None)
        self.assertEqual(data, self.fdata)

    def test_default_url_read_handles_negative_size(self):
        scs = contentsource.UrlContentSource(self.url_for(self.fpath))
        data = scs.read(-1)
        self.assertEqual(data, self.fdata)

    def test_fd_read_handles_None(self):
        loc = self.furl_for(self.fpath)
        scs = contentsource.UrlContentSource(loc)
        data = scs.read(None)
        self.assertEqual(data, self.fdata)

    def test_fd_read_handles_negative_size(self):
        loc = self.furl_for(self.fpath)
        self.assertTrue(loc.startswith("file://"))
        scs = contentsource.UrlContentSource(loc)
        data = scs.read(-1)
        self.assertEqual(data, self.fdata)

    @skipIf(contentsource.requests is None, "requests not available")
    def test_requests_url_read_handles_None(self):
        scs = self.getcs(self.fpath, contentsource.RequestsUrlReader)
        data = scs.read(None)
        self.assertEqual(data, self.fdata)

    @skipIf(contentsource.requests is None, "requests not available")
    def test_requests_url_read_handles_negative_size(self):
        scs = self.getcs(self.fpath, contentsource.RequestsUrlReader)
        data = scs.read(None)
        self.assertEqual(data, self.fdata)

    @skipIf(contentsource.requests is None, "requests not available")
    def test_requests_url_read_handles_no_size(self):
        scs = self.getcs(self.fpath, contentsource.RequestsUrlReader)
        data = scs.read()
        self.assertEqual(data, self.fdata)

    @skipIf(contentsource.requests is None, "requests not available")
    def test_requests_url_read_handles_int(self):
        scs = self.getcs(self.fpath, contentsource.RequestsUrlReader)
        data = scs.read(3)
        self.assertEqual(data, self.fdata[0:3])

    def test_urllib_url_read_handles_None(self):
        scs = self.getcs(self.fpath, contentsource.Urllib2UrlReader)
        data = scs.read(None)
        self.assertEqual(data, self.fdata)

    def test_urllib_url_read_handles_negative_size(self):
        scs = self.getcs(self.fpath, contentsource.Urllib2UrlReader)
        data = scs.read(None)
        self.assertEqual(data, self.fdata)

    def test_urllib_url_read_handles_no_size(self):
        scs = self.getcs(self.fpath, contentsource.Urllib2UrlReader)
        data = scs.read()
        self.assertEqual(data, self.fdata)

    def test_urllib_url_read_handles_int(self):
        scs = self.getcs(self.fpath, contentsource.Urllib2UrlReader)
        data = scs.read(3)
        self.assertEqual(data, self.fdata[0:3])


class TestResume(BaseDirUsingTestCase):
    http = True

    def setUp(self):
        super(TestResume, self).setUp()
        self.target = tempfile.mkdtemp()
        with open(join(self.target, 'foo.part'), 'wb') as f:
            f.write(b'hello')
        with open(join(self.test_d, 'foo'), 'wb') as f:
            f.write(b'hello world\n')

    def test_binopen_seek(self):
        tcs = objectstores.FileStore(self.target)
        scs = contentsource.UrlContentSource(self.furl_for('foo'))
        tcs.insert('foo', scs)
        with open(join(self.target, 'foo'), 'rb') as f:
            contents = f.read()
            assert contents == b'hello world\n', contents

    def test_url_seek(self):
        tcs = objectstores.FileStore(self.target)
        loc = self.url_for('foo')
        scs = contentsource.UrlContentSource(loc)
        tcs.insert('foo', scs)
        with open(join(self.target, 'foo'), 'rb') as f:
            contents = f.read()
            # Unfortunately, SimpleHTTPServer doesn't support the Range
            # header, so we get two 'hello's.
            assert contents == b'hellohello world\n', contents

    @raises(Exception)
    def test_post_open_set_start_pos(self):
        cs = contentsource.UrlContentSource(self.furl_for('foo'))
        cs.open()
        cs.set_start_pos(1)

    def test_percent_callback(self):
        data = {'dld': 0}

        def handler(path, downloaded, total):
            data['dld'] = downloaded

        tcs = objectstores.FileStore(self.target,
                                     complete_callback=handler)
        loc = self.url_for('foo')
        scs = contentsource.UrlContentSource(loc)
        tcs.insert('foo', scs, size=len('hellohello world'))

        assert data['dld'] > 0  # just make sure it was called


class BaseReaderTest(BaseDirUsingTestCase):
    __test__ = False
    reader = None
    fpath = 'foo'
    fdata = b'hello world\n'
    http = False

    def setUp(self):
        super(BaseReaderTest, self).setUp()
        with open(join(self.test_d, self.fpath), 'wb') as f:
            f.write(self.fdata)

    def geturl(self, path):
        if self.http:
            return self.url_for(path)
        else:
            return self.furl_for(path)

    def test_read_handles_None(self):
        fp = self.reader(self.geturl(self.fpath))
        data = fp.read(None)
        fp.close()
        self.assertEqual(data, self.fdata)

    def test_read_handles_no_size(self):
        fp = self.reader(self.geturl(self.fpath))
        data = fp.read()
        fp.close()
        self.assertEqual(data, self.fdata)

    def test_read_handles_negative_size(self):
        fp = self.reader(self.geturl(self.fpath))
        data = fp.read(-1)
        fp.close()
        self.assertEqual(data, self.fdata)

    def test_read_handles_size(self):
        size = len(self.fdata) - 2
        fp = self.reader(self.geturl(self.fpath))
        data = fp.read(size)
        fp.close()
        self.assertEqual(data, self.fdata[0:size])

    def test_normal_usage(self):
        buflen = 2
        content = b''
        buf = b'\0' * buflen
        fp = None
        try:
            fp = self.reader(self.geturl(self.fpath))
            while len(buf) == buflen:
                buf = fp.read(buflen)
                content += buf
        finally:
            if fp is not None:
                fp.close()

        self.assertEqual(content, self.fdata)


@skipIf(contentsource.requests is None, "requests not available")
class RequestsBase(object):
    reader = contentsource.RequestsUrlReader
    http = True


class Urllib2Base(object):
    reader = contentsource.Urllib2UrlReader
    http = True


class TestRequestsUrlReader(RequestsBase, BaseReaderTest):
    __test__ = True


class TestUrllib2UrlReader(Urllib2Base, BaseReaderTest):
    __test__ = True


class TestFileReader(BaseReaderTest):
    __test__ = True
    reader = contentsource.FileReader

    def test_supports_file_scheme(self):
        file_url = self.geturl(self.fpath)
        self.assertTrue(file_url.startswith("file://"))
        fp = self.reader(file_url)
        data = fp.read()
        fp.close()
        self.assertEqual(data, self.fdata)


class UserAgentTests(BaseDirUsingTestCase):
    fpath = "agent-test-filename-x"
    fdata = b"this is my file content\n"
    http = True

    def read_url(self, reader, agent):
        with open(join(self.test_d, self.fpath), 'wb') as f:
            f.write(self.fdata)
        fp = reader(self.url_for(self.fpath), user_agent=agent)
        try:
            return fp.read()
        finally:
            fp.close()

    @skipIf(contentsource.requests is None, "requests not available")
    def test_requests_sends_user_agent_when_supplied(self):
        self.read_url(contentsource.RequestsUrlReader, "myagent1")
        self.assertIn("myagent1", self.server.read_output())

    def test_urllib2_sends_user_agent_when_supplied(self):
        self.read_url(contentsource.Urllib2UrlReader, "myagent2")
        self.assertIn("myagent2", self.server.read_output())

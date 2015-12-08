import random
import shutil
import tempfile

from os.path import join
from simplestreams import objectstores
from simplestreams import contentsource
from subprocess import Popen, PIPE
from unittest import TestCase
from nose.tools import raises


class RandomPortServer(object):
    def __init__(self, path):
        self.path = path
        self.process = None
        self.port = None

    def __enter__(self):
        for _ in range(10):
            port = random.randrange(40000, 65000)
            p = Popen(['python', '-u', '-m', 'SimpleHTTPServer', str(port)],
                      cwd=self.path, stdout=PIPE)
            # wait for the HTTP server to start up
            while True:
                line = p.stdout.readline()  # pylint: disable=E1101
                if b'Serving HTTP' in line:
                    self.port = port
                    self.process = p
                    return self

    def __exit__(self, _type, value, tb):
        self.process.kill()  # pylint: disable=E1101

    def url_for(self, fpath=""):
        if self.port is None:
            raise ValueError("No port available")
        return 'http://127.0.0.1:%d/' % self.port + fpath


class TestUrlContentSource(TestCase):

    fpath = 'foo'
    fdata = b'hello world\n'

    def setUp(self):
        self.source = tempfile.mkdtemp()
        with open(join(self.source, self.fpath), 'wb') as f:
            f.write(b'hello world\n')

    def tearDown(self):
        shutil.rmtree(self.source)

    def test_url_read_handles_None(self):
        with RandomPortServer(self.source) as server:
            scs = contentsource.UrlContentSource(server.url_for(self.fpath))
            data = scs.read(None)
        self.assertEqual(data, self.fdata)

    def test_url_read_handles_negative_size(self):
        with RandomPortServer(self.source) as server:
            scs = contentsource.UrlContentSource(server.url_for(self.fpath))
            data = scs.read(-1)
        self.assertEqual(data, self.fdata)

    def test_fd_read_handles_None(self):
        loc = 'file://%s/%s' % (self.source, self.fpath)
        scs = contentsource.UrlContentSource(loc)
        data = scs.read(None)
        self.assertEqual(data, self.fdata)

    def test_fd_read_handles_negative_size(self):
        loc = 'file://%s/%s' % (self.source, self.fpath)
        scs = contentsource.UrlContentSource(loc)
        data = scs.read(-1)
        self.assertEqual(data, self.fdata)


class TestResume(TestCase):
    def setUp(self):
        self.target = tempfile.mkdtemp()
        self.source = tempfile.mkdtemp()
        with open(join(self.target, 'foo.part'), 'wb') as f:
            f.write(b'hello')
        with open(join(self.source, 'foo'), 'wb') as f:
            f.write(b'hello world\n')

    def tearDown(self):
        shutil.rmtree(self.target)
        shutil.rmtree(self.source)

    def test_binopen_seek(self):
        tcs = objectstores.FileStore(self.target)
        scs = contentsource.UrlContentSource('file://%s/foo' % self.source)
        tcs.insert('foo', scs)
        with open(join(self.target, 'foo'), 'rb') as f:
            contents = f.read()
            assert contents == b'hello world\n', contents

    def test_url_seek(self):
        with RandomPortServer(self.source) as server:
            tcs = objectstores.FileStore(self.target)
            loc = server.url_for('foo')
            scs = contentsource.UrlContentSource(loc)
            tcs.insert('foo', scs)
            with open(join(self.target, 'foo'), 'rb') as f:
                contents = f.read()
                # Unfortunately, SimpleHTTPServer doesn't support the Range
                # header, so we get two 'hello's.
                assert contents == b'hellohello world\n', contents

    @raises(Exception)
    def test_post_open_set_start_pos(self):
        cs = contentsource.UrlContentSource('file://%s/foo' % self.source)
        cs.open()
        cs.set_start_pos(1)

    def test_percent_callback(self):
        data = {'dld': 0}

        def handler(path, downloaded, total):
            data['dld'] = downloaded

        with RandomPortServer(self.source) as server:
            tcs = objectstores.FileStore(self.target,
                                         complete_callback=handler)
            loc = server.url_for('foo')
            scs = contentsource.UrlContentSource(loc)
            tcs.insert('foo', scs, size=len('hellohello world'))

            assert data['dld'] > 0  # just make sure it was called

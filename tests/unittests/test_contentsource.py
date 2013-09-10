import shutil
import tempfile

from os.path import join
from simplestreams import objectstores
from simplestreams import contentsource
from subprocess import Popen, PIPE
from unittest import TestCase

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
        p = Popen(['python', '-u', '-m', 'SimpleHTTPServer', '8000'],
                  cwd=self.source, stdout=PIPE)

        try:
            # wait for the HTTP server to start up
            while True:
                if b'Serving HTTP' in p.stdout.readline():
                    break

            tcs = objectstores.FileStore(self.target)
            scs = contentsource.UrlContentSource('http://localhost:8000/foo')
            tcs.insert('foo', scs)
            with open(join(self.target, 'foo'), 'rb') as f:
                contents = f.read()
                # Unfortunately, SimpleHTTPServer doesn't support the Range
                # header, so we get two 'hello's.
                assert contents == b'hellohello world\n', contents
        finally:
            p.kill()

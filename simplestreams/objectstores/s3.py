import boto.exception
import boto.s3
import boto.s3.connection
from contextlib import closing
import errno
import tempfile

import simplestreams.objectstores as objectstores
import simplestreams.contentsource as cs

class S3ObjectStore(objectstores.ObjectStore):

    _bucket = None
    _connection = None

    def __init__(self, prefix):
        # expect 's3://bucket/path_prefix'
        self.prefix = prefix
        if prefix.startswith("s3://"):
            path = prefix[5:]
        else:
            path = prefix

        (self.bucketname, self.path_prefix) = path.split("/", 1)

    @property
    def _conn(self):
        if not self._connection:
            self._connection = boto.s3.connection.S3Connection()

        return self._connection

    @property
    def bucket(self):
        if not self._bucket:
            self._bucket = self._conn.get_bucket(self.bucketname)
        return self._bucket

    def insert(self, path, reader, checksums=None, mutable=True):
        #store content from reader.read() into path, expecting result checksum
        try:
            tfile = tempfile.TemporaryFile()
            with reader(path) as rfp:
                while True:
                    buf = rfp.read(self.read_size)
                    tfile.write(buf)
                    if len(buf) != self.read_size:
                        break
            with closing(self.bucket.new_key(self.path_prefix + path)) as key:
                key.set_contents_from_file(tfile)
        finally:
            tfile.close()

    def insert_content(self, path, content, checksums=None, mutable=True):
        with closing(self.bucket.new_key(self.path_prefix + path)) as key:
            key.set_contents_from_string(content)

    def remove(self, path):
        #remove path from store
        self.bucket.delete_key(self.path_prefix + path)

    def reader(self, path):
        # essentially return an 'open(path, r)'
        key = self.bucket.get_key(self.path_prefix + path)
        if not key:
            myerr = IOError("Unable to open %s" % path)
            myerr.errno = errno.ENOENT
            raise myerr

        return cs.FdContentSource(fd=key, url=self.path_prefix + path)

    def exists_with_checksum(self, path, checksums=None):
        key = self.bucket.get_key(self.path_prefix + path)
        if key is None:
            return False

        if 'md5' in checksums:
            return checksums['md5'] == key.etag.replace('"', "")

        return False


# vi: ts=4 expandtab

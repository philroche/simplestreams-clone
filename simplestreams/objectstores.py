import boto.exception
import boto.s3
import boto.s3.connection
import errno
import hashlib
import os
import os.path
from simplestreams.util import mkdir_p, load_content, url_reader
import tempfile
import StringIO
from contextlib import closing


READ_BUFFER_SIZE = 1024 * 1024


class ObjectStore(object):
    read_size = READ_BUFFER_SIZE

    def __init__(self, prefix):
        self.prefix = prefix

    def insert(self, path, reader, checksums={}, mutable=True):
        #store content from reader.read() into path, expecting result checksum
        pass

    def insert_content(self, path, content, checksums={}):
        self.insert(path, StringReader(content).open, checksums)

    def remove(self, path):
        #remove path from store
        pass

    def reader(self, path):
        # essentially return an 'open(path, r)'
        pass

    def exists_with_checksum(self, path, checksums={}):
        return has_valid_checksum(path=path, reader=self.reader,
                                  checksums=checksums, read_size=self.read_size)


class checksummer(object):
    _hasher = None
    algorithm = None
    expected = None

    def __init__(self, checksums):
        # expects a dict of hashname/value
        if not checksums:
            self._hasher = None
            return
        for meth in ("md5", "sha512"):
            if meth in checksums and meth in hashlib.algorithms:
                self._hasher = hashlib.new(meth)
                self.algorithm = meth

        self.expected = checksums.get(self.algorithm, None)

        if not self._hasher:
            raise TypeError("Unable to find suitable hash algorithm")

    def update(self, data):
        if self._hasher is None:
            return
        self._hasher.update(data)

    def hexdigest(self):
        if self._hasher is None:
            return None
        return self._hasher.hexdigest()

    def check(self):
        return (self.expected is None or self.expected == self.hexdigest())


def has_valid_checksums(path, reader, checksums={}, read_size=READ_BUFFER_SIZE):
    cksum = checksummer(checksums)
    try:
        with reader(path) as rfp:
            if not checksums:
                # we've already done the open, and no checksum data
                return True
            while True:
                buf = rfp.read(read_size)
                cksum.update(buf)
                if len(buf) != read_size:
                    break
            return cksum.check()
    except Exception:
        return False


class FileStore(ObjectStore):
    def insert(self, path, reader, checksums={}, mutable=True):
        wpath = os.path.join(self.prefix, path)
        if os.path.isfile(wpath):
            if not mutable:
                # if the file exists, and not mutable, return
                return
            if has_valid_checksum(path=path, reader=self.reader,
                                  checksums=checksums, read_size=self.read_size):
                return

        cksum = checksummer(checksums)
        try:
            mkdir_p(os.path.dirname(wpath))
            with open(wpath, "w") as wfp:
                with reader(path) as rfp:
                    while True:
                        buf = rfp.read(self.read_size)
                        wfp.write(buf)
                        cksum.update(buf)
                        if len(buf) != self.read_size:
                            break
            if not cksum.check():
                msg = "unexpected checksum '%s' on %s (found: %s expected: %s"
                raise Exception(msg % (cksum.algorithm, path,
                                       cksum.hexdigest(), cksum.expected))
        except Exception as e:
            try:
                os.unlink(wpath)
            except:
                pass
            raise e

    def remove(self, path, reader, checksums={}):
        try:
            os.unlink(os.path.join(self.prefix, path))
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def reader(self, path):
        return open(os.path.join(self.prefix, path), "r")


class S3ObjectStore(ObjectStore):

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
            
    def insert(self, path, reader, checksums={}, mutable=True):
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

    def insert_content(self, path, content, checksums={}):
        with closing(self.bucket.new_key(self.path_prefix + path)) as key:
            key.set_contents_from_string(content)

    def remove(self, path):
        #remove path from store
        self.bucket.delete_key(self.path_prefix + path)

    def reader(self, path):
        # essentially return an 'open(path, r)'
        key = self.bucket.get_key(self.path_prefix + path)
        if not key:
            raise myerr
        raise e

        return closing(key)

    def exists_with_checksum(self, path, checksums={}):
        key = self.bucket.get_key(self.path_prefix + path)
        if key is None:
            return False

        if 'md5' in checksums:
            return checksums['md5'] == key.etag.replace('"',"")

        return False

class StringReader(StringIO.StringIO):
    def __init__(self, content):
        StringIO.StringIO.__init__(self, content)
        return

    def open(self, path):
        return self

    def __enter__(self):
        return self

    def __exit__(self, type, value, trace):
        self.close()

class MirrorStoreReader(object):
    def __init__(self, objectstore):
        self.objectstore = objectstore
        try:
            content = self.reader("MIRROR.info").read()
            info = load_content(content)

        except Exception as e:
            raise IOError("Failed to read MIRROR.info from %s: %s" %
                          (objectstore, str(e)))

        self.iqn = info.get('iqn')
        if not self.iqn:
            raise TypeError("MIRROR.info did not contain iqn")

        self.mirrors = info.get('mirrors', [])
        self.authoritative = info.get('authoritative_mirror')

    def reader(self, path):
        try:
            reader = self.objectstore.reader(path)
            return reader
        except IOError as e:
            if e.errno != errno.ENOENT:
                raise e

        author = self.authoritative
        mirrors = [m for m in self.mirrors if m and m != author]
        if author:
            mirrors.append(author)

        for mirror in mirrors:
            try:
                return url_reader(mirror + path)
            except IOError as e:
                continue

        raise IOError("Unable to open path '%s'" % path)



class MirrorStoreWriter(object):
    def __init__(self, objectstore):
        self.objectstore = objectstore

    def reader(self, path):
        return self.objectstore.reader(path)

    def insert_object(self, path, reader, checksums=None, mutable=True):
        self.objectstore.insert(path=path, reader=reader,
                                checksums=checksums, mutable=mutable)

    def insert_object_content(self, path, content, checksums={}):
        self.objectstore.insert_content(path, content, checksums)

    def insert_item(self, item):
        pass

    def remove_item(self, item):
        pass

    def insert_group_pre(self, group):
        pass

    def insert_group_post(self, group):
        pass

    def remove_group_pre(self, group):
        pass

    def remove_group_post(self, group):
        pass

    def remove_object(self, path):
        self.objectstore.remove(path)

    def insert_group(self, group, reader):
        self.insert_group_pre(group)
        for item in group.items:
            if item.path:
                self.insert_object(item.path, reader,
                                   checksums=item.checksums, mutable=False)
            self.insert_item(item)
        self.insert_group_post(group)

    def remove_group(self, group):
        self.remove_group_pre(group)
        for item in group.items:
            self.remove_item(item)
            if item.path:
                self.remove_object(path, item)
        self.remove_group_post(group)


# vi: ts=4 expandtab

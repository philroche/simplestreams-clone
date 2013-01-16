import errno
import hashlib
import os
import os.path
from simplestreams.util import mkdir_p
import StringIO


class ObjectStore(object):
    def __init__(self, prefix):
        pass

    def insert(self, path, reader, checksum={}):
        #store content from reader.read() into path, expecting result checksum
        pass

    def insert_content(self, path, content, checksum={}):
        self.insert(path, StringReader(content).open, checksum)

    def remove(self, path):
        #remove path from store
        pass

    def reader(self, path):
        # essentially return an 'open(path, r)'
        pass


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


class FileStore(ObjectStore):
    read_size = 4096

    def __init__(self, prefix):
        self.prefix = prefix

    def insert(self, path, reader, checksum={}):
        wpath = os.path.join(self.prefix, path)
        cksum = checksummer(checksum)
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

    def remove(self, path, reader, checksum={}):
        try:
            os.unlink(os.path.join(self.prefix, path))
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def reader(self, path):
        return open(os.path.join(self.prefix, path), "r")


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


class MirrorStore(object):
    def __init__(self, objectstore):
        print "HELLO WORD"
        self.objectstore = objectstore

    def reader(self, path):
        return self.objectstore.reader(path)

    def insert_object(self, path, reader, checksum=None, item=None):
        self.objectstore.insert(path, reader, checksum)

    def insert_object_content(self, path, content, checksum={}):
        self.objectstore.insert_content(path, content, checksum)

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
                                   checksum=item.checksums)
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

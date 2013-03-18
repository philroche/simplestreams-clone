import errno
import logging
import hashlib
import os

import simplestreams.contentsource as cs
import simplestreams.util as util

READ_BUFFER_SIZE = 1024 * 1024

LOG = logging.getLogger('simplestreams')
LOG.setLevel(logging.ERROR)
LOG.addHandler(logging.StreamHandler())


class ObjectStore(object):
    read_size = READ_BUFFER_SIZE

    def insert(self, path, reader, checksums=None, mutable=True):
        #store content from reader.read() into path, expecting result checksum
        raise NotImplementedError()

    def insert_content(self, path, content, checksums=None):
        self.insert(path, cs.MemoryContentSource(content=content), checksums)

    def remove(self, path):
        #remove path from store
        raise NotImplementedError()

    def reader(self, path):
        # return a ContentSource for the provided path
        raise NotImplementedError()

    def exists_with_checksum(self, path, checksums=None):
        return has_valid_checksum(path=path, reader=self.reader,
                                  checksums=checksums,
                                  read_size=self.read_size)


class MemoryObjectStore(ObjectStore):
    def __init__(self, data=None):
        super(MemoryObjectStore, self).__init__()
        if data is None:
            data = {}
        self.data = data

    def insert(self, path, reader, checksums=None, mutable=True):
        self.data[path] = reader.read()

    def remove(self, path):
        #remove path from store
        del self.data[path]

    def reader(self, path):
        return cs.MemoryContentSource(content=self.data['path'],
                                      url="%s://%s" % (self.__class__, path))


class FileStore(ObjectStore):

    def __init__(self, prefix):
        self.prefix = prefix

    def insert(self, path, reader, checksums=None, mutable=True):
        wpath = self._fullpath(path)
        if os.path.isfile(wpath):
            if not mutable:
                # if the file exists, and not mutable, return
                return
            if has_valid_checksum(path=path, reader=self.reader,
                                  checksums=checksums,
                                  read_size=self.read_size):
                return

        cksum = util.checksummer(checksums)
        try:
            util.mkdir_p(os.path.dirname(wpath))
            with open(wpath, "w") as wfp:
                while True:
                    buf = reader.read(self.read_size)
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
            except IOError:
                pass
            raise e

    def remove(self, path):
        try:
            os.unlink(self._fullpath(path))
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def reader(self, path):
        return cs.UrlContentSource(url=self._fullpath(path))

    def _fullpath(self, path):
        return os.path.join(self.prefix, path)


def has_valid_checksum(path, reader, checksums=None,
                       read_size=READ_BUFFER_SIZE):
    if checksums is None:
        return False
    cksum = util.checksummer(checksums)
    try:
        with reader(path) as rfp:
            while True:
                buf = rfp.read(read_size)
                cksum.update(buf)
                if len(buf) != read_size:
                    break
            return cksum.check()
    except Exception:
        return False


# vi: ts=4 expandtab

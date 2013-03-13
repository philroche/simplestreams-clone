import boto.exception
import boto.s3
import boto.s3.connection
from contextlib import closing
import errno
import hashlib
import logging
import os
import os.path
import StringIO
import tempfile
import yaml

import simplestreams.util as util
import simplestreams.stream

LOG = logging.getLogger('simplestreams')
LOG.setLevel(logging.ERROR)
LOG.addHandler(logging.StreamHandler())


READ_BUFFER_SIZE = 1024 * 1024


class ObjectStore(object):
    read_size = READ_BUFFER_SIZE

    def __init__(self, prefix):
        self.prefix = prefix

    def insert(self, path, reader, checksums=None, mutable=True):
        #store content from reader.read() into path, expecting result checksum
        raise NotImplementedError()

    def insert_content(self, path, content, checksums=None):
        reader = Reader(reader=StringReader(content),
                        url=(self.prefix + path)),
        self.insert(path, reader, checksums)

    def remove(self, path):
        #remove path from store
        raise NotImplementedError()

    def reader(self, path):
        # return a Reader
        raise NotImplementedError()

    def exists_with_checksum(self, path, checksums=None):
        return has_valid_checksum(path=path, reader=self.reader,
                                  checksums=checksums,
                                  read_size=self.read_size)


class MemoryObjectStore(ObjectStore):
    def __init__(self, data):
        self.data = data

    def insert(self, path, reader, checksums=None, mutable=True):
        self.data[path] = reader.read(path)

    def remove(self, path):
        #remove path from store
        del self.data[path]

    def reader(self, path):
        # essentially return an 'open(path, r)'
        return Reader(reader=StringReader(self.data['path']),
                      url="%s://%s" % (self.__class__, path))


class SimpleStreamMirrorReader(object):
    def load_stream(self, path, reference=None):
        return load_stream_path(path, self.reader, reference)

    def reader(self, path):
        raise NotImplementedError()


class SimpleStreamMirrorWriter(object):
    def load_stream(self, path, reference=None):
        # return a Stream representation loaded from stream file
        # at path.  If not present, return an empty Stream based
        # on reference (set iqn and mirrors)
        raise NotImplementedError()

    def store_stream(self, path, stream, content):
        # store the stream file content
        raise NotImplementedError()

    def store_collection(self, path, collection, content):
        # store the collection file content
        raise NotImplementedError()

    def insert_group(self, group, reader):
        # insert the item group, storing items in it
        raise NotImplementedError()

    def remove_group(self, group):
        # remove item group and items in it
        raise NotImplementedError()

    def filter_stream(self, stream):
        return True

    def filter_group(self, group):
        return True


class checksummer(object):
    _hasher = None
    algorithm = None
    expected = None

    def __init__(self, checksums):
        # expects a dict of hashname/value
        if not checksums:
            self._hasher = None
            return
        for meth in ("md5", "sha256", "sha512"):
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


def has_valid_checksum(path, reader, checksums=None, read_size=READ_BUFFER_SIZE):
    if checksums is None:
        return False
    cksum = checksummer(checksums)
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


class UrlMirrorReader(SimpleStreamMirrorReader):
    def __init__(self, prefix):

        if prefix.startswith("/"):
            self._reader = open
        else:
            self._reader = util.url_reader

        self.prefix = prefix
        info = load_mirror_info(self.reader)
        self.iqn = info.get('iqn')
        self.mirrors = info.get('mirrors', [])
        self.authoritative = info.get('authoritative_mirror')

    def reader(self, path):
        try:
            reader = self._reader(self.prefix + path)
            return Reader(reader=reader, url=self.prefix + path)
        except Exception as e:
            util.pass_if_enoent(e)

        return try_mirrors(path, mirrors=self.mirrors,
                           authoritative=self.authoritative)


class FileStore(ObjectStore):
    def insert(self, path, reader, checksums=None, mutable=True):
        wpath = os.path.join(self.prefix, path)
        if os.path.isfile(wpath):
            if not mutable:
                # if the file exists, and not mutable, return
                return
            if has_valid_checksum(path=path, reader=self.reader,
                                  checksums=checksums,
                                  read_size=self.read_size):
                return

        cksum = checksummer(checksums)
        try:
            util.mkdir_p(os.path.dirname(wpath))
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
            except IOError:
                pass
            raise e

    def remove(self, path):
        try:
            os.unlink(os.path.join(self.prefix, path))
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def reader(self, path):
        fpath = os.path.join(self.prefix, path)
        return Reader(reader=open(fpath, "r"), url=fpath)


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

    def insert_content(self, path, content, checksums=None):
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

        return Reader(reader=key, url=self.path_prefix + path)

    def exists_with_checksum(self, path, checksums=None):
        key = self.bucket.get_key(self.path_prefix + path)
        if key is None:
            return False

        if 'md5' in checksums:
            return checksums['md5'] == key.etag.replace('"', "")

        return False


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


class MirrorStoreReader(SimpleStreamMirrorReader):
    def __init__(self, objectstore):
        self.objectstore = objectstore

        try:
            info = load_mirror_info(self.reader)

        except Exception as e:
            raise IOError("Failed to read MIRROR.info from %s: %s" %
                          (objectstore, str(e)))

        self.iqn = info.get('iqn')
        self.mirrors = info.get('mirrors', [])
        self.authoritative = info.get('authoritative_mirror')

    def reader(self, path):
        try:
            return self.objectstore.reader(path)
        except IOError as e:
            if e.errno != errno.ENOENT:
                raise e

        return try_mirrors(path, mirrors=self.mirrors,
                           authoritative=self.authoritative)

    def load_stream(self, path, reference=None):
        # return a Stream object
        return load_stream_path(path, self.objectstore.reader, reference)


class MirrorStoreWriter(SimpleStreamMirrorWriter):
    def __init__(self, objectstore):
        self.objectstore = objectstore

    def load_stream(self, path, reference=None):
        # return a Stream object
        dp = self.data_path(path)
        if self.objectstore.exists_with_checksum(dp):
            with self.objectstore.reader(dp) as fp:
                return simplestreams.stream.Stream(yaml.safe_load(fp.read()))
        else:
            return load_stream_path(path, self.objectstore.reader, reference)

    def store_stream(self, path, stream, content):
        # store the stream file content
        if path is None:
            raise TypeError("Empty path for stream")

        self.insert_path_content(self.data_path(path),
                                 yaml.safe_dump(stream.as_dict()))
        self.insert_path_content(path, content)

    def store_collection(self, path, collection, content):
        # store the collection file content
        self.insert_path_content(self.data_path(path),
                                 yaml.safe_dump(collection.as_dict()))
        self.insert_path_content(path, content)

    def insert_group(self, group, reader):
        self.insert_group_pre(group)
        for item in group.items:
            if item.path:
                self.insert_object(item.path, reader,
                                   checksums=item.checksums,
                                   mutable=False)
            self.insert_item(item, reader)
        self.insert_group_post(group)

    def remove_group(self, group):
        self.remove_group_pre(group)
        for item in group.items:
            self.remove_item(item)
        self.remove_group_post(group)

    def insert_object(self, path, reader, checksums=None, mutable=True):
        self.objectstore.insert(path=path, reader=reader,
                                checksums=checksums, mutable=mutable)

    def insert_path_content(self, path, content, checksums=None):
        self.objectstore.insert_content(path, content, checksums)

    def remove_object(self, path):
        self.objectstore.remove(path)

    def insert_item(self, item, reader):
        if item.path:
            self.objectstore.insert(item.path, reader,
                                    checksums=item.checksums, mutable=False)

    def remove_item(self, item):
        if item.path:
            self.remove_object(item.path)

    def insert_group_pre(self, group):
        pass

    def insert_group_post(self, group):
        pass

    def remove_group_pre(self, group):
        pass

    def remove_group_post(self, group):
        pass

    def data_path(self, path):
        return ".data/%s" % path


def load_stream_path(path, reader, reference=None):
    try:
        (data, _sig) = util.read_possibly_signed(path, reader)
        return simplestreams.stream.Stream(util.load_content(data))

    except IOError as e:
        if e.errno != errno.ENOENT:
            raise Exception("Failed to load %s" % path)
        data = reference.copy()
        data['item_groups'] = []
        return simplestreams.stream.Stream(data)


def load_mirror_info(reader, path="MIRROR.info"):
    try:
        with reader(path) as fp:
            content = fp.read()
    except Exception as e:
        raise IOError("Failed to read %s: %s" % (path, str(e)))

    info = util.load_content(content)

    if 'iqn' not in info:
        raise TypeError("%s did not contain iqn" % path)

    for f in ('mirrors', 'authoritative_mirrors'):
        info[f] = info.get(f, [])

    return info


def try_mirrors(path, mirrors=None, authoritative=None):
    if mirrors is None:
        mirrors = []

    search = [m for m in mirrors]

    if authoritative and authoritative not in search:
        search.append(authoritative)

    for mirror in search:
        try:
            url = mirror + path
            return Reader(reader=util.url_reader(url), url=url)
        except Exception as e:
            util.pass_if_enoent(e)

    raise IOError("Unable to open path '%s'. tried %s" % (path, search))


# vi: ts=4 expandtab

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
import hashlib
import os

import simplestreams.contentsource as cs
import simplestreams.util as util
from simplestreams.log import LOG

READ_BUFFER_SIZE = 1024 * 10


class ObjectStore(object):
    read_size = READ_BUFFER_SIZE

    def insert(self, path, reader, checksums=None, mutable=True, size=None):
        #store content from reader.read() into path, expecting result checksum
        raise NotImplementedError()

    def insert_content(self, path, content, checksums=None, mutable=True):
        if not isinstance(content, bytes):
            content = content.encode('utf-8')
        self.insert(path=path, reader=cs.MemoryContentSource(content=content),
                    checksums=checksums, mutable=mutable)

    def remove(self, path):
        #remove path from store
        raise NotImplementedError()

    def source(self, path):
        # return a ContentSource for the provided path
        raise NotImplementedError()

    def exists_with_checksum(self, path, checksums=None):
        return has_valid_checksum(path=path, reader=self.source,
                                  checksums=checksums,
                                  read_size=self.read_size)


class MemoryObjectStore(ObjectStore):
    def __init__(self, data=None):
        super(MemoryObjectStore, self).__init__()
        if data is None:
            data = {}
        self.data = data

    def insert(self, path, reader, checksums=None, mutable=True, size=None):
        self.data[path] = reader.read()

    def remove(self, path):
        #remove path from store
        del self.data[path]

    def source(self, path):
        return cs.MemoryContentSource(content=self.data['path'],
                                      url="%s://%s" % (self.__class__, path))


class FileStore(ObjectStore):

    def __init__(self, prefix, complete_callback=None):
        """ complete_callback is called periodically to notify users when a
        file is being inserted. It takes three arguments: the path that is
        inserted, the number of bytes downloaded, and the number of total
        bytes. """
        self.prefix = prefix
        self.complete_callback = complete_callback

    def insert(self, path, reader, checksums=None, mutable=True, size=None):
        wpath = self._fullpath(path)
        if os.path.isfile(wpath):
            if not mutable:
                # if the file exists, and not mutable, return
                return
            if has_valid_checksum(path=path, reader=self.source,
                                  checksums=checksums,
                                  read_size=self.read_size):
                return

        cksum = util.checksummer(checksums)
        out_d = os.path.dirname(wpath)
        partfile = os.path.join(out_d, "%s.part" % os.path.basename(wpath))

        util.mkdir_p(out_d)
        orig_part_size = 0

        if os.path.exists(partfile):
            try:
                orig_part_size = os.path.getsize(partfile)
                reader.set_start_pos(orig_part_size)

                LOG.debug("resuming partial (%s) download of '%s' from '%s'",
                          orig_part_size, path, partfile)
                with open(partfile, "rb") as fp:
                    while True:
                        buf = fp.read(self.read_size)
                        cksum.update(buf)
                        if len(buf) != self.read_size:
                            break

            except NotImplementedError:
                # continuing not supported, just delete and retry
                orig_part_size = 0
                os.unlink(partfile)

        with open(partfile, "ab") as wfp:

            while True:
                buf = reader.read(self.read_size)
                wfp.write(buf)
                cksum.update(buf)

                if size is not None:
                    if self.complete_callback:
                        self.complete_callback(path, wfp.tell(), size)
                    if wfp.tell() > size:
                        # file is too big, so the checksum won't match; we
                        # might as well stop downloading.
                        break

                if len(buf) != self.read_size:
                    break

        if not cksum.check():
            os.unlink(partfile)
            if orig_part_size:
                LOG.warn("resumed download of '%s' had bad checksum.", path)

            msg = "unexpected checksum '%s' on %s (found: %s expected: %s)"
            raise Exception(msg % (cksum.algorithm, path,
                                   cksum.hexdigest(), cksum.expected))
        os.rename(partfile, wpath)

    def remove(self, path):
        try:
            os.unlink(self._fullpath(path))
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
        cur_d = os.path.dirname(path)
        prev_d = None
        while cur_d and cur_d != prev_d:
            try:
                os.rmdir(cur_d)
            except OSError as e:
                if e.errno not in (errno.ENOENT, errno.ENOTEMPTY):
                    raise
            prev_d = cur_d
            cur_d = os.path.dirname(path)

    def source(self, path):
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

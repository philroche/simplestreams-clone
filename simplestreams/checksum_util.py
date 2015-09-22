#   Copyright (C) 2015 Canonical Ltd.
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
import hashlib

# these are in order of increasing preference
CHECKSUMS = ("md5", "sha256", "sha512")

try:
    ALGORITHMS = list(getattr(hashlib, 'algorithms'))
except AttributeError:
    ALGORITHMS = list(hashlib.algorithms_available)


class checksummer(object):
    _hasher = None
    algorithm = None
    expected = None

    def __init__(self, checksums):
        if not checksums:
            self._hasher = None
            return

        for meth in CHECKSUMS:
            if meth in checksums and meth in ALGORITHMS:
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

    def __str__(self):
        return ("checksummer (algorithm=%s expected=%s)" %
                (self.algorithm, self.expected))


def item_checksums(item):
    return {k: item[k] for k in CHECKSUMS if k in item}


class SafeCheckSummer(checksummer):
    """SafeCheckSummer raises ValueError if checksums are not provided."""
    def __init__(self, checksums, allowed=None):
        if allowed is None:
            allowed = CHECKSUMS
        super(SafeCheckSummer, self).__init__(checksums)
        if self.algorithm not in allowed:
            raise ValueError(
                "provided checksums (%s) did not include any allowed (%s)" %
                (checksums, allowed))


class InvalidChecksum(ValueError):
    def __init__(self, path, cksum, size=None, expected_size=None, msg=None):
        self.path = path
        self.cksum = cksum
        self.size = size
        self.expected_size = expected_size
        self.msg = msg

    def __str__(self):
        if self.msg is not None:
            return self.msg
        if not isinstance(self.expected_size, int):
            msg = "Invalid size '%s' at %s." % (self.expected_size, self.path)
        else:
            msg = ("Invalid %s Checksum at %s. Found %s. Expected %s. "
                   "read %s bytes expected %s bytes." %
                   (self.cksum.algorithm, self.path,
                    self.cksum.hexdigest(), self.cksum.expected,
                    self.size, self.expected_size))
            if self.size:
                msg += (" (size %s expected %s)" %
                        (self.size, self.expected_size))
        return msg


def invalid_checksum_for_reader(reader, msg=None):
    return InvalidChecksum(path=reader.url, cksum=reader.checksummer,
                           size=reader.bytes_read, expected_size=reader.size,
                           msg=msg)

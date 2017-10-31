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

import simplestreams.objectstores as objectstores
import simplestreams.contentsource as cs
import simplestreams.openstack as openstack

import errno
import hashlib
from swiftclient import Connection, ClientException


def get_swiftclient(**kwargs):
    # nmap has entries that need name changes from a 'get_service_conn_info'
    # to a swift Connection name.
    # pt has names that pass straight through
    nmap = {'endpoint': 'preauthurl', 'token': 'preauthtoken'}
    pt = ('insecure', 'cacert')

    connargs = {v: kwargs.get(k) for k, v in nmap.items() if k in kwargs}
    connargs.update({k: kwargs.get(k) for k in pt if k in kwargs})
    if kwargs.get('session'):
        sess = kwargs.get('session')
        try:
            # If session is available try it
            return Connection(session=sess)
        except TypeError:
            # The edge case where session is availble but swiftclient is
            # < 3.3.0. Use the old style method for Connection.
            pass
    return Connection(**connargs)


class SwiftContentSource(cs.IteratorContentSource):
    def is_enoent(self, exc):
        return is_enoent(exc)


class SwiftObjectStore(objectstores.ObjectStore):

    def __init__(self, prefix, region=None):
        # expect 'swift://bucket/path_prefix'
        self.prefix = prefix
        if prefix.startswith("swift://"):
            path = prefix[8:]
        else:
            path = prefix

        (self.container, self.path_prefix) = path.split("/", 1)

        super(SwiftObjectStore, self).__init__()

        self.keystone_creds = openstack.load_keystone_creds()
        if region is not None:
            self.keystone_creds['region_name'] = region

        conn_info = openstack.get_service_conn_info('object-store',
                                                    **self.keystone_creds)
        self.swiftclient = get_swiftclient(**conn_info)

        # http://docs.openstack.org/developer/swift/misc.html#acls
        self.swiftclient.put_container(self.container,
                                       headers={'X-Container-Read':
                                                '.r:*,.rlistings'})

    def insert(self, path, reader, checksums=None, mutable=True, size=None):
        # store content from reader.read() into path, expecting result checksum
        self._insert(path=path, contents=reader, checksums=checksums,
                     mutable=mutable)

    def insert_content(self, path, content, checksums=None, mutable=True):
        self._insert(path=path, contents=content, checksums=checksums,
                     mutable=mutable)

    def remove(self, path):
        self.swiftclient.delete_object(container=self.container,
                                       obj=self.path_prefix + path)

    def source(self, path):
        def itgen():
            (_headers, iterator) = self.swiftclient.get_object(
                container=self.container, obj=self.path_prefix + path,
                resp_chunk_size=self.read_size)
            return iterator

        return SwiftContentSource(itgen=itgen, url=self.prefix + path)

    def exists_with_checksum(self, path, checksums=None):
        return headers_match_checksums(self._head_path(path), checksums)

    def _head_path(self, path):
        try:
            headers = self.swiftclient.head_object(container=self.container,
                                                   obj=self.path_prefix + path)
        except Exception as exc:
            if is_enoent(exc):
                return {}
            raise
        return headers

    def _insert(self, path, contents, checksums=None, mutable=True, size=None):
        # content is a ContentSource or a string
        headers = self._head_path(path)
        if headers:
            if not mutable:
                return
            if headers_match_checksums(headers, checksums):
                return

        insargs = {'container': self.container, 'obj': self.path_prefix + path,
                   'contents': contents}

        if size is not None and isinstance(contents, str):
            size = len(contents)

        if size is not None:
            insargs['content_length'] = size

        if checksums and checksums.get('md5'):
            insargs['etag'] = checksums.get('md5')
        elif isinstance(contents, str):
            insargs['etag'] = hashlib.md5(contents).hexdigest()

        self.swiftclient.put_object(**insargs)


def headers_match_checksums(headers, checksums):
    if not (headers and checksums):
        return False
    if ('md5' in checksums and headers.get('etag') == checksums.get('md5')):
        return True
    return False


def is_enoent(exc):
    return ((isinstance(exc, IOError) and exc.errno == errno.ENOENT) or
            (isinstance(exc, ClientException) and exc.http_status == 404))

# vi: ts=4 expandtab

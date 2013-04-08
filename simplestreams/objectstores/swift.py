import simplestreams.objectstores as objectstores
import simplestreams.contentsource as cs
import simplestreams.openstack as openstack

import hashlib
from swiftclient import Connection, ClientException


def get_swiftclient(**kwargs):
    # nmap has entries that need name changes from a 'get_service_conn_info'
    # to a swift Connection name.
    # pt has names that pass straight through
    nmap = {'endpoint': 'preauthurl', 'token': 'preauthtoken'}
    pt = ('insecure', 'cacert')

    connargs = {v: kwargs.get(k) for k, v in nmap.iteritems() if k in kwargs}
    connargs.update({k: kwargs.get(k) for k in pt if k in kwargs})
    return Connection(**connargs)


class SwiftContentSource(cs.IteratorContentSource):
    def is_enoent(self, exc):
        return is_enoent(exc)


class SwiftObjectStore(objectstores.ObjectStore):

    def __init__(self, prefix):
        # expect 'swift://bucket/path_prefix'
        self.prefix = prefix
        if prefix.startswith("swift://"):
            path = prefix[8:]
        else:
            path = prefix

        (self.container, self.path_prefix) = path.split("/", 1)

        super(SwiftObjectStore, self).__init__()

        self.keystone_creds = openstack.load_keystone_creds()
        conn_info = openstack.get_service_conn_info('object-store',
                                                    **self.keystone_creds)
        self.swiftclient = get_swiftclient(**conn_info)

        # http://docs.openstack.org/developer/swift/misc.html#acls
        self.swiftclient.put_container(self.container,
            headers={'X-Container-Read': '.r:*,.rlistings'})


    def insert(self, path, reader, checksums=None, mutable=True):
        #store content from reader.read() into path, expecting result checksum
        self._insert(path=path, contents=reader, checksums=checksums,
                     mutable=mutable)

    def insert_content(self, path, content, checksums=None, mutable=True):
        self._insert(path=path, contents=content, checksums=checksums,
                     mutable=mutable)

    def remove(self, path):
        self.swiftclient.delete_object(container=self.container,
                                       obj=self.path_prefix + path)

    def reader(self, path):
        def itgen():
            (headers, iterator) = self.swiftclient.get_object(
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

        if size is not None and isinstance(contents, (unicode, str)):
            size = len(contents)

        if size is not None:
            insargs['content_length'] = size

        if checksums and checksums.get('md5'):
            insargs['etag'] = checksums.get('md5')
        elif isinstance(contents, (unicode, str)):
            insargs['etag'] = hashlib.md5(contents).hexdigest()

        etag = self.swiftclient.put_object(**insargs)


def headers_match_checksums(headers, checksums):
    if not (headers and checksums):
        return False
    if ('md5' in checksums and
        headers.get('etag') == checksums.get('md5')):
        return True
    return False


def is_enoent(exc):
    return ((isinstance(exc, IOError) and exc.errno == errno.ENOENT) or
            (isinstance(exc, ClientException) and exc.http_status == 404))

# vi: ts=4 expandtab

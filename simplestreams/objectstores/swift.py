import simplestreams.objectstores as objectstores
import simplestreams.contentsource as cs


class SwiftObjectStore(objectstores.ObjectStore):

    def __init__(self, prefix):
        # expect 's3://bucket/path_prefix'
        self.prefix = prefix
        if prefix.startswith("s3://"):
            path = prefix[5:]
        else:
            path = prefix

        (self.bucketname, self.path_prefix) = path.split("/", 1)

    def insert(self, path, reader, checksums=None, mutable=True):
        #store content from reader.read() into path, expecting result checksum
        raise NotImplementedError()

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

# vi: ts=4 expandtab

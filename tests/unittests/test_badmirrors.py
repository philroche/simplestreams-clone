from unittest import TestCase
from tests.testutil import get_mirror_reader
from simplestreams.mirrors import (
    ObjectStoreMirrorWriter, ObjectStoreMirrorReader)
from simplestreams.objectstores import MemoryObjectStore
from simplestreams import util
from simplestreams import checksum_util


class TestBadDataSources(TestCase):
    """Test of Bad Data in a datasource."""

    dlpath = "streams/v1/download.json"
    pedigree = ("com.example:product1", "20150915", "item1")
    item_path = "product1/20150915/text.txt"
    example = "minimal"

    def setUp(self):
        self.src = self.get_clean_src(self.example, path=self.dlpath)
        self.target = ObjectStoreMirrorWriter(
            config={}, objectstore=MemoryObjectStore())

    def get_clean_src(self, exname, path):
        good_src = get_mirror_reader(exname)
        objectstore = MemoryObjectStore(None)
        target = ObjectStoreMirrorWriter(config={}, objectstore=objectstore)
        target.sync(good_src, path)

        # clean the .data out of the mirror so it doesn't get read
        keys = list(objectstore.data.keys())
        for k in keys:
            if k.startswith(".data"):
                del objectstore.data[k]

        return ObjectStoreMirrorReader(
            objectstore=objectstore, policy=lambda content, path: content)

    def test_sanity_valid(self):
        # verify that the tests are fine on expected pass
        _moditem(self.src, self.dlpath, self.pedigree, lambda c: c)
        self.target.sync(self.src, self.dlpath)

    def test_missing_size_causes_bad_checksum(self):
        def del_size(item):
            del item['size']
            return item

        _moditem(self.src, self.dlpath, self.pedigree, del_size)
        self.assertRaises(checksum_util.InvalidChecksum,
                          self.target.sync, self.src, self.dlpath)

    def test_larger_size_causes_bad_checksum(self):
        def size_plus_1(item):
            item['size'] = int(item['size']) + 1
            return item

        _moditem(self.src, self.dlpath, self.pedigree, size_plus_1)
        self.assertRaises(checksum_util.InvalidChecksum,
                          self.target.sync, self.src, self.dlpath)

    def test_smaller_size_causes_bad_checksum(self):
        def size_minus_1(item):
            item['size'] = int(item['size']) - 1
            return item
        _moditem(self.src, self.dlpath, self.pedigree, size_minus_1)
        self.assertRaises(checksum_util.InvalidChecksum,
                          self.target.sync, self.src, self.dlpath)

    def test_too_much_content_causes_bad_checksum(self):
        self.src.objectstore.data[self.item_path] += b"extra"
        self.assertRaises(checksum_util.InvalidChecksum,
                          self.target.sync, self.src, self.dlpath)

    def test_too_little_content_causes_bad_checksum(self):
        orig = self.src.objectstore.data[self.item_path]
        self.src.objectstore.data[self.item_path] = orig[0:-1]
        self.assertRaises(checksum_util.InvalidChecksum,
                          self.target.sync, self.src, self.dlpath)

    def test_busted_checksum_causes_bad_checksum(self):
        def break_checksum(item):
            chars = "0123456789abcdef"
            orig = item['sha256']
            item['sha256'] = ''.join(
                [chars[(chars.find(c) + 1) % len(chars)] for c in orig])
            return item

        _moditem(self.src, self.dlpath, self.pedigree, break_checksum)
        self.assertRaises(checksum_util.InvalidChecksum,
                          self.target.sync, self.src, self.dlpath)

    def test_changed_content_causes_bad_checksum(self):
        # correct size but different content should raise bad checksum
        self.src.objectstore.data[self.item_path] = ''.join(
            ["x" for c in self.src.objectstore.data[self.item_path]])
        self.assertRaises(checksum_util.InvalidChecksum,
                          self.target.sync, self.src, self.dlpath)


def _moditem(src, path, pedigree, modfunc):
    # load the products data at 'path' in 'src' mirror, then call modfunc
    # on the data found at pedigree. and store the updated data.
    sobj = src.objectstore
    tree = util.load_content(sobj.source(path).read())
    item = util.products_exdata(tree, pedigree, insert_fieldnames=False)
    util.products_set(tree, modfunc(item), pedigree)
    sobj.insert_content(path, util.dump_data(tree))

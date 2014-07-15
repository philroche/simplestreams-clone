from unittest import TestCase
from simplestreams.util import resolve_work

from simplestreams.objectstores import MemoryObjectStore
from simplestreams.mirrors import ObjectStoreMirrorWriter
from simplestreams.filters import filter_item, ItemFilter

from tests.testutil import get_mirror_reader


class TestStreamResolveWork(TestCase):

    def tryit(self, src, target, maxnum=None, keep=False,
              itemfilter=None, add=None, remove=None):
        if add is None:
            add = []
        if remove is None:
            remove = []

        (r_add, r_remove) = resolve_work(src, target, maxnum=maxnum, keep=keep,
                                         itemfilter=itemfilter)
        self.assertEqual(r_add, add)
        self.assertEqual(r_remove, remove)

    def test_keep_with_max_none_is_exception(self):
        self.assertRaises(TypeError, resolve_work, [1], [2], None, True)

    def test_full_replace(self):
        src = [10, 9, 8]
        target = [7, 6, 5]
        self.tryit(src=src, target=target, add=src, remove=[5, 6, 7])

    def test_only_new_with_max(self):
        self.tryit(src=[10, 9, 8], target=[7, 6, 5],
                   add=[10, 9], remove=[5, 6, 7], maxnum=2)

    def test_only_new_with_keep(self):
        self.tryit(src=[10, 9, 8], target=[7, 6, 5],
                   add=[10, 9, 8], remove=[5, 6], maxnum=4, keep=True)

    def test_only_remove(self):
        self.tryit(src=[3], target=[3, 2, 1], add=[], remove=[1, 2])

    def test_only_remove_with_keep(self):
        self.tryit(src=[3], target=[3, 2, 1],
                   add=[], remove=[], maxnum=3, keep=True)

    def test_only_remove_with_max(self):
        self.tryit(src=[3], target=[3, 2, 1],
                   add=[], remove=[1, 2], maxnum=2)

    def test_only_remove_with_no_max(self):
        self.tryit(src=[3], target=[3, 2, 1],
                   add=[], remove=[1, 2], maxnum=None)

    def test_null_remote_without_keep(self):
        self.tryit(src=[], target=[3, 2, 1], add=[], remove=[1, 2, 3])

    def test_null_remote_with_keep(self):
        self.tryit(src=[], target=[3, 2, 1], maxnum=3, keep=True, add=[],
                   remove=[])

    def test_null_remote_without_keep_with_maxnum(self):
        self.tryit(src=[], target=[3, 2, 1], maxnum=3, keep=False, add=[],
                   remove=[1, 2, 3])

    def test_max_forces_remove(self):
        self.tryit(src=[2, 1], target=[2, 1], maxnum=1, keep=False,
                   add=[], remove=[1])

    def test_nothing_needed_with_max(self):
        self.tryit(src=[1], target=[1], maxnum=1, keep=False, add=[],
                   remove=[])

    def test_filtered_items_not_present(self):
        self.tryit(src=[1, 2, 3, 4, 5], target=[1], maxnum=None, keep=False,
                   itemfilter=lambda a: a < 3, add=[2], remove=[])

    def test_max_and_target_has_newest(self):
        self.tryit(src=[1, 2, 3, 4], target=[4], maxnum=1, keep=False,
                   add=[], remove=[])

    def test_unordered_target_input(self):
        self.tryit(src=['20121026.1', '20120328', '20121001'],
                   target=['20121001', '20120328', '20121026.1'], maxnum=2,
                   keep=False, add=[], remove=['20120328'])

    def test_reduced_max(self):
        self.tryit(src=[9, 5, 8, 4, 7, 3, 6, 2, 1],
                   target=[9, 8, 7, 6, 5], maxnum=4, keep=False,
                   add=[], remove=[5])

    def test_foocloud_multiple_paths_remove(self):
        config = {'delete_filtered_items': True}
        memory = ObjectStoreMirrorWriter(config, MemoryObjectStore(None))
        foocloud = get_mirror_reader("foocloud")
        memory.sync(foocloud, "streams/v1/index.json")

        # We sync'd, now we'll sync everything that doesn't have the samepaths
        # tag. samepaths reuses some paths, and so if we try and delete
        # anything here that would be wrong.
        filters = [ItemFilter("version_name!=samepaths")]

        def no_samepaths(data, src, _target, pedigree):
            return filter_item(filters, data, src, pedigree)

        def dont_remove(*_args):
            # This shouldn't be called, because we are smart and do "reference
            # counting".
            assert False

        memory.filter_version = no_samepaths
        memory.store.remove = dont_remove

        memory.sync(foocloud, "streams/v1/index.json")

# vi: ts=4 expandtab

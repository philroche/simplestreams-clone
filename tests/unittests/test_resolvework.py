from unittest import TestCase
from simplestreams.util import resolve_work

class TestStreamResolveWork(TestCase):

    def tryit(self, src=[], target=[], max=None, keep=False, filter=None,
              add=[], remove=[]):
        (r_add, r_remove) = resolve_work(src, target, max=max, keep=keep,
                                         filter=filter)
        self.assertEqual(r_add, add)
        self.assertEqual(r_remove, remove)

    def test_keep_with_max_none_is_exception(self):
        self.assertRaises(TypeError, resolve_work, [1], [2], None, True)

    def test_full_replace(self):
        src = [10, 9, 8]
        target = [7, 6, 5]
        self.tryit(src=src, target=target, add=src, remove=target)

    def test_only_new_with_max(self):
        self.tryit(src=[10, 9, 8], target=[7, 6, 5],
                   add=[10, 9], remove=[7, 6, 5], max=2)

    def test_only_new_with_keep(self):
        self.tryit(src=[10, 9, 8], target=[7, 6, 5],
                   add=[10, 9, 8], remove=[6, 5], max=4, keep=True)

    def test_only_remove(self):
        self.tryit(src=[3], target=[3, 2, 1], add=[], remove=[2, 1])

    def test_only_remove_with_keep(self):
        self.tryit(src=[3], target=[3, 2, 1], 
                   add=[], remove=[], max=3, keep=True)

    def test_only_remove_with_max(self):
        self.tryit(src=[3], target=[3, 2, 1],
                   add=[], remove=[2, 1], max=2)
    
    def test_only_remove_with_no_max(self):
        self.tryit(src=[3], target=[3, 2, 1],
                   add=[], remove=[2, 1], max=None)

    def test_null_remote_without_keep(self):
        self.tryit(src=[], target=[3,2,1], add=[], remove=[3, 2, 1])

    def test_null_remote_with_keep(self):
        self.tryit(src=[], target=[3,2,1], max=3, keep=True, add=[], remove=[])

    def test_null_remote_without_keep(self):
        self.tryit(src=[], target=[3,2,1], max=3, keep=False, add=[],
                   remove=[3,2,1])

    def test_max_forces_remove(self):
        self.tryit(src=[2,1], target=[2,1], max=1, keep=False,
                   add=[], remove=[1])

    def test_nothing_needed_with_max(self):
        self.tryit(src=[1], target=[1], max=1, keep=False, add=[], remove=[])

    def test_filtered_items_not_present(self):
        self.tryit(src=[1,2,3,4,5], target=[1], max=None, keep=False,
                   filter=lambda a: a < 3, add=[2], remove=[])

# vi: ts=4 expandtab

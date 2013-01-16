from unittest import TestCase
from simplestreams.util import resolve_work

class TestStreamResolveWork(TestCase):

    def tryit(self, src=[], target=[], max=None, keep=None, add=[], remove=[]):
        (r_add, r_remove) = resolve_work(src, target, max=max, keep=keep)
        self.assertEqual(r_add, add)
        self.assertEqual(r_remove, remove)

    def test_keep_greater_than_max_is_exception(self):
        keep = 2
        mmax = 3
        self.assertRaises(TypeError, self.tryit, [1,2], [3,4], mmax, keep)

    def test_full_replace(self):
        src = [10, 9, 8]
        target = [7, 6, 5]
        self.tryit(src=src, target=target, add=src, remove=target)

    def test_only_new_with_max(self):
        self.tryit(src=[10, 9, 8], target=[7, 6, 5],
                   add=[10, 9], remove=[7, 6, 5], max=2)

    def test_only_new_with_keep(self):
        self.tryit(src=[10, 9, 8], target=[7, 6, 5],
                   add=[10, 9, 8], remove=[6,5], keep=4)

    def test_only_new_with_keep(self):
        self.tryit(src=[10, 9, 8], target=[7, 6, 5],
                   add=[10, 9, 8], remove=[6, 5], keep=4)

    def test_only_remove(self):
        self.tryit(src=[3], target=[3, 2, 1], add=[], remove=[2, 1])

    def test_only_remove_with_keep(self):
        self.tryit(src=[3], target=[3, 2, 1], 
                   add=[], remove=[], keep=3)

    def test_only_remove_with_max(self):
        self.tryit(src=[3], target=[3, 2, 1],
                   add=[], remove=[2, 1], max=2)

    def test_null_remote_without_keep(self):
        self.tryit(src=[], target=[3,2,1], add=[], remove=[3, 2, 1])

    def test_null_remote_with_keep(self):
        self.tryit(src=[], target=[3,2,1], keep=4, add=[], remove=[])

# vi: ts=4 expandtab

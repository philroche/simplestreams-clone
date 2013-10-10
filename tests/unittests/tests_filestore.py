import shutil
import tempfile

import os
from simplestreams import objectstores
from simplestreams import mirrors
from tests.testutil import get_mirror_reader
from unittest import TestCase

FOOCLOUD_FILE = ("files/release-20121026.1/"
                 "foovendor-6.1-server-cloudimg-amd64.tar.gz")


class TestResumePartDownload(TestCase):
    def setUp(self):
        self.target = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.target)

    def test_mirror_resume(self):
        # test mirror resuming from filestore
        smirror = get_mirror_reader("foocloud")

        # as long as this is less than size of file, its valid
        part_size = 10

        # create a valid .part file
        tfile = os.path.join(self.target, FOOCLOUD_FILE)
        os.makedirs(os.path.dirname(tfile))
        with open(tfile + ".part", "wb") as fw:
            with smirror.source(FOOCLOUD_FILE) as fr:
                fw.write(fr.read(part_size))

        target_objstore = objectstores.FileStore(self.target)
        tmirror = mirrors.ObjectStoreMirrorWriter(config=None,
                                                  objectstore=target_objstore)
        tmirror.sync(smirror, "streams/v1/index.json")

        # the part file should have been cleaned up.  If this fails, then
        # likely the part file wasn't used, and this test is no longer valid
        self.assertFalse(os.path.exists(tfile + ".part"))

    def test_corrupted_mirror_resume(self):
        # test corrupted .part file is caught
        smirror = get_mirror_reader("foocloud")

        # create a corrupt .part file
        tfile = os.path.join(self.target, FOOCLOUD_FILE)
        os.makedirs(os.path.dirname(tfile))
        with open(tfile + ".part", "w") as fw:
            # just write some invalid data
            fw.write("--bogus--")

        target_objstore = objectstores.FileStore(self.target)
        tmirror = mirrors.ObjectStoreMirrorWriter(config=None,
                                                  objectstore=target_objstore)
        self.assertRaisesRegexp(Exception, r".*%s.*" % FOOCLOUD_FILE,
                                tmirror.sync,
                                smirror, "streams/v1/index.json")

        # now the .part file should be removed, and trying again should succeed
        self.assertFalse(os.path.exists(tfile + ".part"))
        tmirror.sync(smirror, "streams/v1/index.json")
        self.assertFalse(os.path.exists(tfile + ".part"))

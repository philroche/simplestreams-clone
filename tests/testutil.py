import os
from simplestreams import objectstores
from simplestreams import mirrors


EXAMPLES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            "..", "examples"))


def get_mirror_reader(name, docdir=None):
    if docdir is None:
        docdir = EXAMPLES_DIR

    src_d = os.path.join(EXAMPLES_DIR, name)
    sstore = objectstores.FileStore(src_d)
    return mirrors.ObjectStoreMirrorReader(sstore)

# vi: ts=4 expandtab syntax=python

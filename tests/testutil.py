import os
from simplestreams import objectstores
from simplestreams import mirrors


EXAMPLES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            "..", "examples"))


def get_mirror_reader(name, docdir=None, signed=False):
    if docdir is None:
        docdir = EXAMPLES_DIR

    src_d = os.path.join(EXAMPLES_DIR, name)
    sstore = objectstores.FileStore(src_d)

    def policy(content, path):  # pylint: disable=W0613
        return content

    kwargs = {} if signed else {"policy": policy}
    return mirrors.ObjectStoreMirrorReader(sstore, **kwargs)

# vi: ts=4 expandtab syntax=python

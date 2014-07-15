from tests.testutil import get_mirror_reader
from simplestreams.mirrors import DryRunMirrorWriter
from simplestreams.objectstores import MemoryObjectStore


def test_DryRunMirrorWriter_foocloud_no_filters():
    src = get_mirror_reader("foocloud")
    config = {}
    objectstore = MemoryObjectStore(None)
    target = DryRunMirrorWriter(config, objectstore)
    target.sync(src, "streams/v1/index.json")
    assert target.size == 886

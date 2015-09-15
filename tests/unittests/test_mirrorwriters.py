from tests.testutil import get_mirror_reader
from simplestreams.filters import get_filters
from simplestreams.mirrors import DryRunMirrorWriter, ObjectFilterMirror
from simplestreams.objectstores import MemoryObjectStore


def test_DryRunMirrorWriter_foocloud_no_filters():
    src = get_mirror_reader("foocloud")
    config = {}
    objectstore = MemoryObjectStore(None)
    target = DryRunMirrorWriter(config, objectstore)
    target.sync(src, "streams/v1/index.json")
    assert target.size == 1311


def test_ObjectFilterMirror_does_item_filter():
    src = get_mirror_reader("foocloud")
    filter_list = get_filters(['ftype!=disk1.img'])
    config = {'filters': filter_list}
    objectstore = MemoryObjectStore(None)
    target = ObjectFilterMirror(config, objectstore)
    target.sync(src, "streams/v1/index.json")

    unexpected = [f for f in objectstore.data if 'disk' in f]

    assert len(unexpected) == 0
    assert len(objectstore.data) != 0

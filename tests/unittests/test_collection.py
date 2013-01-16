from unittest import TestCase
from simplestreams.collection import Collection

MINIMAL_DATA = {
    "format": "stream-collection:1.0",
    "streams": [],
}

TRIVIAL_STREAMS = [
    {"path": "i386.yaml", "foo-tag": "from-i386"},
    {"path": "amd64.yaml", "foo-tag": "from-amd64"},
]

COLLECTION_TAGS = {
    "mytag1": "some value",
    "lorum": "ipsum",
    "cubs": "win"
}

class TestCollectionInit(TestCase):
    """Test of Collection for initialization."""

    def test_init_error_no_args(self):
        self.assertRaises(TypeError, Collection)

    def test_missing_required_raises_type_error(self):
        for required in ('format',):
            mydict = MINIMAL_DATA.copy()
            del mydict[required]
            self.assertRaises(TypeError, Collection, mydict)

    def test_minimal_data(self):
        mcoll = Collection(data=MINIMAL_DATA)
        self.assertEqual(mcoll.format, MINIMAL_DATA["format"])
        self.assertTrue(len(mcoll.streams) == 0)

    def test_item_groups(self):
        data = MINIMAL_DATA.copy()
        data['streams'] = TRIVIAL_STREAMS
        mcoll = Collection(data=data)

        self.assertEqual(len(mcoll.streams), len(TRIVIAL_STREAMS))

    def test_stream_entry_sees_tags(self):
        data = MINIMAL_DATA.copy()
        data['tags'] = COLLECTION_TAGS.copy()

        mystream = Collection(data)
        for f in data['tags']:
            self.assertIn(f, mystream.streams.alltags)

# vi: ts=4 expandtab

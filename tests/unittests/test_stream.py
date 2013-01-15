import copy
from unittest import TestCase
from simplestreams.stream import Stream

MINIMAL_DATA = {
    "format": "stream-1.0",
    "iqn": "iqn.2012-12.com.example.foo:bar:wark",
    "item_groups": [],
}

TRIVIAL_ITEM_GROUPS = [
    {"serial": 3,
        "items": [{"name": "entry 3.1"},
                  {"name": "entry 3.2"},
                  {"name": "entry 3.3"}]},
    {"serial": 2,
        "items": [{"name": "entry 2.1"},
                  {"name": "entry 2.2"},
                  {"name": "entry 2.3"}]},
    {"serial": 1,
        "items": [{"name": "entry 1.1"},
                  {"name": "entry 1.2"},
                  {"name": "entry 1.3"}]},
]

STREAM_TAGS = {
    "mytag1": "some value",
    "lorum": "ipsum",
    "cubs": "win"
}


class TestStreamInit(TestCase):
    """Test of Stream for initialization."""

    def test_init_error_no_args(self):
        self.assertRaises(TypeError, Stream)

    def test_missing_required_raises_type_error(self):
        for required in ('format', 'iqn'):
            mydict = MINIMAL_DATA.copy()
            del mydict[required]
            self.assertRaises(TypeError, Stream, mydict)

    def test_minimal_data(self):
        mstream = Stream(data=MINIMAL_DATA)
        self.assertEqual(mstream.iqn, MINIMAL_DATA["iqn"])
        self.assertEqual(mstream.format, MINIMAL_DATA["format"])
        self.assertTrue(len(mstream.item_groups) == 0)

    def test_item_groups(self):
        data = MINIMAL_DATA.copy()
        data['item_groups'] = TRIVIAL_ITEM_GROUPS
        mstream = Stream(data=data)

        self.assertEqual(len(mstream.item_groups), len(TRIVIAL_ITEM_GROUPS))

    def test_init_does_not_change_dict(self):
        data = MINIMAL_DATA.copy()
        del data["item_groups"]
        data_copy = data.copy()
        _mystream = Stream(data)
        self.assertEqual(data, data_copy)

    def test_item_group_list_sees_tags(self):
        data = MINIMAL_DATA.copy()
        data['tags'] = STREAM_TAGS.copy()

        mystream = Stream(data)
        for f in data['tags']:
            self.assertIn(f, mystream.item_groups.alltags)

    def test_walk_lineage(self):
        data = MINIMAL_DATA.copy()
        data['tags'] = STREAM_TAGS.copy()
        data['item_groups'] = copy.copy(TRIVIAL_ITEM_GROUPS)

        mystream = Stream(data)

        self.assertTrue(mystream is mystream.item_groups.parent)

        for ig in mystream.item_groups:
            self.assertTrue(mystream.item_groups is ig.parent)
            self.assertTrue(ig.items.parent is ig)
            for item in ig.items:
                self.assertTrue(ig.items is item.parent)

    def test_tags_passdown_to_items(self):
        data = MINIMAL_DATA.copy()
        data['tags'] = STREAM_TAGS.copy()
        data['item_groups'] = copy.copy(TRIVIAL_ITEM_GROUPS)

        mystream = Stream(data)

        self.assertTrue(mystream is mystream.item_groups.parent)
        places = (mystream.tags,
                  mystream.item_groups.alltags,
                  mystream.item_groups[0].alltags,
                  mystream.item_groups[0]['items'].alltags,
                  mystream.item_groups[0]['items'][0].alltags,
                  )

        for p in places:
            for f in data['tags']:
                self.assertIn(f, p)


# vi: ts=4 expandtab

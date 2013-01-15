from unittest import TestCase

from simplestreams.items import (ItemGroup, ItemGroupList, ItemList)


class TestItemGroupList(TestCase):
    """Test of ItemGroup."""

    def test_simple_in(self):
        gl = ItemGroupList([ItemGroup({'serial': 1})])
        self.assertTrue(ItemGroup({'serial': 1}) in gl)

    def test_sort(self):
        igl = ItemGroupList([])
        for s in range(1, 5):
            igl.append(ItemGroup({'serial': s}))

        igl.sort(reverse=True)
        self.assertEqual(igl[0]['serial'], 4)

        igl.sort()
        self.assertEqual(igl[0]['serial'], 1)


class TestItemGroup(TestCase):
    """Test of ItemGroup."""

    def test_init(self):
        myigroup = ItemGroup({'serial': 1})
        self.assertTrue('serial' in myigroup)
        self.assertTrue('items' in myigroup)

    def test_strange_equal(self):
        mygroup1 = ItemGroup({'serial': 1})
        mygroup2 = ItemGroup({'serial': 1, 'other': 'extra'})
        self.assertEqual(mygroup1, mygroup2)

    def test_tags(self):
        """Tags are any thing in an ItemGroup other than serial and items"""
        mydict = {'serial': 1, 'tag1': 'value1', 'label': 'trouble'}
        tags = mydict.copy()
        del tags['serial']
        mygroup = ItemGroup(mydict)
        self.assertEqual(mygroup.tags,  tags)

    def test_tags_no_include_items(self):
        """verify items do not appear as tags"""
        mydict = {'serial': 1, 'tag1': 'value1', 'label': 'trouble'}
        mydict.update({'items': [{'name': 'foo'}, {'name': 'bar'}]})
        expected = mydict.copy()
        del expected['serial']
        del expected['items']
        mygroup = ItemGroup(mydict)
        self.assertEqual(mygroup.tags, expected)

    def test_tags_pass_down(self):
        mydata = {
            'serial': 20120328,
            'label': 'beta2',
            'items': [
              {'path': 'f/item1', 'name': 'item1', 'tag1': 'value1',
               'md5sum': 'MD5SUM', 'tagname': 'tagvalue'},
              {'path': 'f/item2', 'name': 'item2', 'tag2': 'value2',
               'md5sum': 'MD5SUM'},
            ]
        }
        item3 = {'name': 'item3', 'x': '1'}
        mygroup = ItemGroup(mydata)
        mygroup.items.append(item3)
        mygroup.items.sort()
        self.assertEqual(mygroup.items[0].alltags['label'], "beta2")
        self.assertEqual(mygroup.items[1].alltags,
                         {'tag2': 'value2', 'label': 'beta2'})

class TestItemList(TestCase):
    """Test an ItemList"""

    def test_init(self):
        mylist = ItemList({})

#    def test_init_with_parent(self):
#        myItemGroup = ItemGroup({'serial': 1, 'tags': {'tag1': 'val1'})
#        mylist = ItemList({}, parent


# vi: ts=4 expandtab

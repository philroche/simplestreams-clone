# pylint: disable=C0301
from simplestreams import util

from copy import deepcopy
from unittest import TestCase


class TestProductsSet(TestCase):
    def test_product_exists(self):
        tree = {'products': {'P1': {"F1": "V1"}}}
        util.products_set(tree, {'F2': 'V2'}, ('P1',))
        self.assertEqual(tree, {'products': {'P1': {'F2': 'V2'}}})

    def test_product_no_exists(self):
        tree = {'products': {'A': 'B'}}
        util.products_set(tree, {'F1': 'V1'}, ('P1',))
        self.assertEqual(tree,
                         {'products': {'A': 'B', 'P1': {'F1': 'V1'}}})

    def test_product_no_products_tree(self):
        tree = {}
        util.products_set(tree, {'F1': 'V1'}, ('P1',))
        self.assertEqual(tree,
                         {'products': {'P1': {'F1': 'V1'}}})

    def test_version_exists(self):
        tree = {'products': {'P1': {'versions': {'FOO': {'1': 'one'}}}}}
        util.products_set(tree, {'2': 'two'}, ('P1', 'FOO'))
        self.assertEqual(tree,
                         {'products': {'P1': {'versions':
                                              {'FOO': {'2': 'two'}}}}})

    def test_version_no_exists(self):
        tree = {'products': {'P1': {'versions': {'BAR': {'1': 'one'}}}}}
        util.products_set(tree, {'2': 'two'}, ('P1', 'FOO'))
        d = {'products': {'P1':
                          {'versions': {'BAR': {'1': 'one'},
                                        'FOO': {'2': 'two'}}}}}
        self.assertEqual(tree, d)

    def test_item_exists(self):
        items = {'item1': {'f1': '1'}}
        tree = {'products': {'P1': {'versions':
                                    {'VBAR': {'1': 'one',
                                              'items': items}}}}}
        mnew = {'f2': 'two'}
        util.products_set(tree, mnew, ('P1', 'VBAR', 'item1',))
        expvers = {'VBAR': {'1': 'one', 'items': {'item1': mnew}}}
        self.assertEqual(tree, {'products': {'P1': {'versions': expvers}}})

    def test_item_no_exists(self):
        items = {'item1': {'f1': '1'}}
        tree = {'products': {'P1': {
            'versions': {'V1': {'VF1': 'VV1', 'items': items}}
        }}}
        util.products_set(tree, {'f2': '2'}, ('P1', 'V1', 'item2',))
        expvers = {'V1': {'VF1': 'VV1', 'items': {'item1': {'f1': '1'},
                                                  'item2': {'f2': '2'}}}}
        self.assertEqual(tree, {'products': {'P1': {'versions': expvers}}})


class TestProductsDel(TestCase):
    def test_product_exists(self):
        tree = {'products': {'P1': {"F1": "V1"}}}
        util.products_del(tree, ('P1',))
        self.assertEqual(tree, {'products': {}})

    def test_product_no_exists(self):
        ptree = {'P1': {'F1': 'V1'}}
        tree = {'products': deepcopy(ptree)}
        util.products_del(tree, ('P2',))
        self.assertEqual(tree, {'products': ptree})

    def test_version_exists(self):
        otree = {'products': {
            'P1': {"F1": "V1"},
            'P2': {'versions': {'VER1': {'X1': 'X2'}}}
        }}
        tree = deepcopy(otree)
        util.products_del(tree, ('P2', 'VER1'))
        del otree['products']['P2']['versions']['VER1']
        self.assertEqual(tree, otree)

    def test_version_no_exists(self):
        otree = {'products': {
            'P1': {"F1": "V1"},
            'P2': {'versions': {'VER1': {'X1': 'X2'}}}
        }}
        tree = deepcopy(otree)
        util.products_del(tree, ('P2', 'VER2'))
        self.assertEqual(tree, otree)

    def test_item_exists(self):
        otree = {'products': {
            'P1': {"F1": "V1"},
            'P2': {'versions': {'VER1': {'X1': 'X2',
                                         'items': {'ITEM1': {'IF1': 'IV2'}}}}}
        }}
        tree = deepcopy(otree)
        del otree['products']['P2']['versions']['VER1']['items']['ITEM1']
        util.products_del(tree, ('P2', 'VER1', 'ITEM1'))
        self.assertEqual(tree, otree)

    def test_item_no_exists(self):
        otree = {'products': {
            'P1': {"F1": "V1"},
            'P2': {'versions': {'VER1': {'X1': 'X2',
                                         'items': {'ITEM1': {'IF1': 'IV2'}}}}}
        }}
        tree = deepcopy(otree)
        util.products_del(tree, ('P2', 'VER1', 'ITEM2'))
        self.assertEqual(tree, otree)


class TestProductsPrune(TestCase):
    def test_products_empty(self):
        tree = {'products': {}}
        util.products_prune(tree)
        self.assertEqual(tree, {})

    def test_products_not_empty(self):
        tree = {'products': {'fooproduct': {'a': 'b'}}}
        util.products_prune(tree)
        self.assertEqual(tree, {})

    def test_has_item(self):
        otree = {'products': {'P1': {'versions':
                                     {'V1': {'items': {'I1': 'I'}}}}}}
        tree = deepcopy(otree)
        util.products_prune(tree)
        self.assertEqual(tree, otree)

    def test_deletes_one_version_leaves_one(self):
        versions = {'V1': {'items': {}}, 'V2': {'items': {'I1': 'I'}}}
        otree = {'products': {'P1': {'versions': versions}}}
        tree = deepcopy(otree)
        util.products_prune(tree)
        del otree['products']['P1']['versions']['V1']
        self.assertEqual(tree, otree)


class TestProductsCondense(TestCase):
    def test_condense_1(self):
        tree = {'products': {'P1': {'versions': {'1': {'A': 'B'},
                                                 '2': {'A': 'B'}}}}}
        exp = {'A': 'B',
               'products': {'P1': {'versions': {'1': {}, '2': {}}}}}

        util.products_condense(tree)
        self.assertEqual(tree, exp)

    def test_condense_unicode(self):
        tree = {'products': {'P1': {'versions': {'1': {'A': u'B'},
                                                 '2': {'A': u'B'}}}}}
        exp = {'A': u'B',
               'products': {'P1': {'versions': {'1': {}, '2': {}}}}}

        util.products_condense(tree)
        self.assertEqual(tree, exp)

    def test_condense_different_arch(self):
        tree = {'products': {'P1': {'versions': {'1': {'items': {'thing1': {'arch': 'amd64'},
                                                                 'thing2': {'arch': 'amd64'}}},
                                                 '2': {'items': {'thing3': {'arch': 'i3867'}}}}}}}

        exp  = {'products': {'P1': {'versions': {'1': {'arch': 'amd64',
                                                       'items': {'thing1': {},
                                                                 'thing2': {}}},
                                                 '2': {'arch': 'i3867',
                                                       'items': {'thing3': {}}}}}}}


        util.products_condense(tree)
        self.assertEqual(tree, exp)

    def test_repeats_removed(self):
        tree = {'products': {'P1': {'A': 'B',
                                    'versions': {'1': {'A': 'B'},
                                                 '2': {'A': 'B'}}}}}
        exp = {'A': 'B',
               'products': {'P1': {'versions': {'1': {}, '2': {}}}}}

        util.products_condense(tree)
        self.assertEqual(tree, exp)

    def test_nonrepeats_stay(self):
        tree = {'products': {'P1': {'A': 'C',
                                    'versions': {'1': {'A': 'B'},
                                                 '2': {'A': 'B'}}}}}
        exp = {'A': 'C',
               'products': {'P1': {'versions': {'1': {'A': 'B'},
                                                '2': {'A': 'B'}}}}}

        util.products_condense(tree)
        self.assertEqual(tree, exp)

# vi: ts=4 expandtab

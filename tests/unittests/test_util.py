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
            {'products': {'P1': {'versions': {'FOO': {'2': 'two'}}}}})

    def test_version_no_exists(self):
        tree = {'products': {'P1': {'versions': {'BAR': {'1': 'one'}}}}}
        util.products_set(tree, {'2': 'two'}, ('P1', 'FOO'))
        self.assertEqual(tree,
            {'products': {'P1':
                          {'versions': {'BAR': {'1': 'one'},
                                        'FOO': {'2': 'two'}}}}})

    def test_item_exists(self):
        items = {'item1': {'f1': '1'}}
        tree = {'products': {'P1': {'versions':
                                       {'VBAR': {'1': 'one',
                                                 'items': items}}}}}
        mnew = {'f2': 'two'}
        util.products_set(tree, mnew, ('P1', 'VBAR', 'item1',))
        expvers = {'VBAR': {'1': 'one', 'items': {'item1': mnew}}}
        self.assertEqual(tree,
            {'products': {'P1': {'versions': expvers}}})

    def test_item_no_exists(self):
        items = {'item1': {'f1': '1'}}
        tree = {'products': {'P1': {
            'versions': {'V1': {'VF1': 'VV1', 'items': items}}
        }}}
        util.products_set(tree, {'f2': '2'}, ('P1', 'V1', 'item2',))
        expvers = {'V1': {'VF1': 'VV1', 'items': {'item1': {'f1': '1'},
                                                  'item2': {'f2': '2'}}}}
        self.assertEqual(tree,
            {'products': {'P1': {'versions': expvers}}})
        pass


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

# vi: ts=4 expandtab
from argparse import Namespace
from contextlib import contextmanager
import json
import os
from io import StringIO
from tempfile import NamedTemporaryFile
from unittest import TestCase

from mock import patch

from simplestreams.generate_simplestreams import (
    FileNamer,
    generate_index,
    Item,
    items2content_trees,
    json_dump as json_dump_verbose,
    )
from simplestreams.json2streams import (
    dict_to_item,
    filenames_to_streams,
    JujuFileNamer,
    parse_args,
    read_items_file,
    write_release_index,
    )
from tests.unittests.test_generate_simplestreams import (
    load_stream_dir,
    temp_dir,
    )


class TestJujuFileNamer(TestCase):

    def test_get_index_path(self):
        self.assertEqual('streams/v1/index2.json',
                         JujuFileNamer.get_index_path())

    def test_get_content_path(self):
        self.assertEqual('streams/v1/foo-bar-baz.json',
                         JujuFileNamer.get_content_path('foo:bar-baz'))


def json_dump(json, filename):
    with patch('sys.stderr', StringIO()):
        json_dump_verbose(json, filename)


class TestDictToItem(TestCase):

    def test_dict_to_item(self):
        pedigree = {
            'content_id': 'cid', 'product_name': 'pname',
            'version_name': 'vname', 'item_name': 'iname',
            }
        item_dict = {'size': '27'}
        item_dict.update(pedigree)
        item = dict_to_item(item_dict)
        self.assertEqual(Item(data={'size': 27}, **pedigree), item)


class TestReadItemsFile(TestCase):

    def test_read_items_file(self):
        pedigree = {
            'content_id': 'cid', 'product_name': 'pname',
            'version_name': 'vname', 'item_name': 'iname',
            }
        with NamedTemporaryFile() as items_file:
            item_dict = {'size': '27'}
            item_dict.update(pedigree)
            json_dump([item_dict], items_file.name)
            items = list(read_items_file(items_file.name))
        self.assertEqual([Item(data={'size': 27}, **pedigree)], items)


class TestWriteReleaseIndex(TestCase):

    def write_full_index(self, out_d, content):
        os.makedirs(os.path.join(out_d, 'streams/v1'))
        path = os.path.join(out_d, JujuFileNamer.get_index_path())
        json_dump(content, path)

    def read_release_index(self, out_d):
        path = os.path.join(out_d, FileNamer.get_index_path())
        with open(path) as release_index_file:
            return json.load(release_index_file)

    def test_empty_index(self):
        with temp_dir() as out_d:
            self.write_full_index(out_d, {'index': {}, 'foo': 'bar'})
            with patch('sys.stderr', StringIO()):
                write_release_index(out_d)
            release_index = self.read_release_index(out_d)
        self.assertEqual({'foo': 'bar', 'index': {}}, release_index)

    def test_release_index(self):
        with temp_dir() as out_d:
            self.write_full_index(out_d, {
                'index': {'com.ubuntu.juju:released:tools': 'foo'},
                'foo': 'bar'})
            with patch('sys.stderr', StringIO()):
                write_release_index(out_d)
            release_index = self.read_release_index(out_d)
        self.assertEqual({'foo': 'bar', 'index': {
            'com.ubuntu.juju:released:tools': 'foo'}
            }, release_index)

    def test_multi_index(self):
        with temp_dir() as out_d:
            self.write_full_index(out_d, {
                'index': {
                    'com.ubuntu.juju:proposed:tools': 'foo',
                    'com.ubuntu.juju:released:tools': 'foo',
                    },
                'foo': 'bar'})
            with patch('sys.stderr', StringIO()):
                write_release_index(out_d)
            release_index = self.read_release_index(out_d)
        self.assertEqual({'foo': 'bar', 'index': {
            'com.ubuntu.juju:released:tools': 'foo'}
            }, release_index)


class TestFilenamesToStreams(TestCase):

    updated = 'updated'

    @contextmanager
    def filenames_to_streams_cxt(self):
        item = {
            'content_id': 'foo:1',
            'product_name': 'bar',
            'version_name': 'baz',
            'item_name': 'qux',
            'size': '27',
            }
        item2 = dict(item)
        item2.update({
            'size': '42',
            'item_name': 'quxx'})
        file_a = NamedTemporaryFile()
        file_b = NamedTemporaryFile()
        with temp_dir() as out_d, file_a, file_b:
            json_dump([item], file_a.name)
            json_dump([item2], file_b.name)
            stream_dir = os.path.join(out_d, 'streams/v1')
            with patch('sys.stderr', StringIO()):
                yield item, item2, file_a, file_b, out_d, stream_dir

    def test_filenames_to_streams(self):
        with self.filenames_to_streams_cxt() as (item, item2, file_a, file_b,
                                                 out_d, stream_dir):
            filenames_to_streams([file_a.name, file_b.name], self.updated,
                                 out_d)
            content = load_stream_dir(stream_dir)
        self.assertEqual(
            sorted(content.keys()),
            sorted(['index.json', 'foo:1.json']))
        items = [dict_to_item(item), dict_to_item(item2)]
        trees = items2content_trees(items, {
            'updated': self.updated, 'datatype': 'content-download'})
        expected = generate_index(trees, 'updated', FileNamer)
        self.assertEqual(expected, content['index.json'])
        self.assertEqual(trees['foo:1'], content['foo:1.json'])

    def test_filenames_to_streams_juju_format(self):
        with self.filenames_to_streams_cxt() as (item, item2, file_a, file_b,
                                                 out_d, stream_dir):
            filenames_to_streams([file_a.name, file_b.name], self.updated,
                                 out_d, juju_format=True)
            content = load_stream_dir(stream_dir)
        self.assertEqual(
            sorted(content.keys()),
            sorted(['index.json', 'index2.json', 'foo-1.json']))
        items = [dict_to_item(item), dict_to_item(item2)]
        trees = items2content_trees(items, {
            'updated': self.updated, 'datatype': 'content-download'})
        expected = generate_index(trees, 'updated', JujuFileNamer)
        self.assertEqual(expected, content['index2.json'])
        index_expected = generate_index({}, 'updated', FileNamer)
        self.assertEqual(index_expected, content['index.json'])
        self.assertEqual(trees['foo:1'], content['foo-1.json'])


class TestParseArgs(TestCase):

    def test_defaults(self):
        args = parse_args(['file1', 'outdir'])
        self.assertEqual(
            Namespace(items_file=['file1'], out_d='outdir', juju_format=False),
            args)

    def test_multiple_files(self):
        args = parse_args(['file1', 'file2', 'file3', 'outdir'])
        self.assertEqual(
            ['file1', 'file2', 'file3'], args.items_file)
        self.assertEqual('outdir', args.out_d)

    def test_juju_format(self):
        args = parse_args(['file1', 'outdir', '--juju-format'])
        self.assertIs(True, args.juju_format)

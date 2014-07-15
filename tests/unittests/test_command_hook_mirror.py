from unittest import TestCase
import simplestreams.mirrors.command_hook as chm
from tests.testutil import get_mirror_reader


class TestCommandHookMirror(TestCase):
    """Test of CommandHookMirror."""

    def setUp(self):
        self._run_commands = []

    def test_init_without_load_stream_fails(self):
        self.assertRaises(TypeError, chm.CommandHookMirror, {})

    def test_init_with_load_products_works(self):
        chm.CommandHookMirror({'load_products': 'true'})

    def test_stream_load_empty(self):

        src = get_mirror_reader("foocloud")
        target = chm.CommandHookMirror({'load_products': ['true']})
        oruncmd = chm.run_command

        try:
            chm.run_command = self._run_command
            target.sync(src, "streams/v1/index.json")

        finally:
            chm.run_command = oruncmd

        # the 'load_products' should be called once for each content
        # in the stream.
        self.assertEqual(self._run_commands, [['true'], ['true']])

    def test_stream_insert_product(self):

        src = get_mirror_reader("foocloud")
        target = chm.CommandHookMirror(
            {'load_products': ['load-products'],
             'insert_products': ['insert-products']})
        oruncmd = chm.run_command

        try:
            chm.run_command = self._run_command
            target.sync(src, "streams/v1/index.json")

        finally:
            chm.run_command = oruncmd

        # the 'load_products' should be called once for each content
        # in the stream. same for 'insert-products'
        self.assertEqual(len([f for f in self._run_commands
                             if f == ['load-products']]), 2)
        self.assertEqual(len([f for f in self._run_commands
                             if f == ['insert-products']]), 2)

    def _run_command(self, cmd, env=None, capture=False, rcs=None):
        self._run_commands.append(cmd)
        rc = 0
        output = ''
        return (rc, output)

# vi: ts=4 expandtab syntax=python

from unittest import TestCase
from simplestreams.command_hook_mirror import CommandHookMirror
from simplestreams.util import sync_stream_file
from tests.testutil import get_mirror_reader

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

class TestCommandHookMirror(TestCase):
    """Test of CommandHookMirror."""

    def test_init_without_load_stream_fails(self):
        self.assertRaises(TypeError, CommandHookMirror, {})

    def test_init_with_load_stream_works(self):
        mirror = CommandHookMirror({'load_stream': 'true'})

    def test_foo(self):
        src = get_mirror_reader("example")
        target = CommandHookMirror({'load_stream': 'true'})
        sync_stream_file("unsigned/i386.yaml", src, target)


# vi: ts=4 expandtab syntax=python

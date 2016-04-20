from unittest import TestCase
from tests.testutil import get_mirror_reader
from simplestreams.mirrors import UrlMirrorReader
from simplestreams.contentsource import URL_READER

class FakeContentSource(object):
    pass


class TestUrlMirrorReader(TestCase):
    """."""

    def setUp(self):
        pass

    def test_source(self):
        """source() method returns a ContentSource."""
        # Verify source() returns a content source constructed using the
        # appropriate path and mirrors.
        reader = UrlMirrorReader("/prefix/", mirrors=["a/", "b/"])
        cs = reader.source("some/path")

        # Resulting ContentSource is passed an URL as a concatenation of
        # the prefix and the path.
        self.assertEqual("/prefix/some/path", cs.url)
        # Mirror URLs have path appended.
        self.assertItemsEqual(["a/some/path", "b/some/path"], cs.mirrors)
        # Default URL_READER is returned.
        self.assertEqual(URL_READER, cs.url_reader)

    def test_source_no_trailing_slash(self):
        """Even if prefix lacks a trailing slash, it behaves the same."""
        # Verify source() returns a content source constructed using the
        # appropriate path and mirrors.
        reader = UrlMirrorReader("/prefix/", mirrors=["a/", "b/"])
        cs = reader.source("some/path")

        self.assertEqual("/prefix/some/path", cs.url)
        self.assertItemsEqual(["a/some/path", "b/some/path"], cs.mirrors)
        self.assertEqual(URL_READER, cs.url_reader)

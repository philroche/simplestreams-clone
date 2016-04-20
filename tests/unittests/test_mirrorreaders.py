from unittest import TestCase
from simplestreams.mirrors import UrlMirrorReader
from simplestreams.contentsource import URL_READER
import simplestreams.mirrors


def fake_url_reader(*args, **kwargs):
    """
    Fake URL reader which returns all the arguments passed in as a dict.

    Positional arguments are returned under the key "ARGS".
    """
    all_args = kwargs.copy()
    all_args["ARGS"] = args
    return all_args


class TestUrlMirrorReader(TestCase):

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
        reader = UrlMirrorReader("/prefix/", mirrors=["a/", "b/"])
        cs = reader.source("some/path")

        self.assertEqual("/prefix/some/path", cs.url)
        self.assertItemsEqual(["a/some/path", "b/some/path"], cs.mirrors)
        self.assertEqual(URL_READER, cs.url_reader)

    def test_source_user_agent(self):
        """When user_agent is set, it is passed to the ContentSource."""
        reader = UrlMirrorReader("/prefix/", mirrors=["a/", "b/"],
                                 user_agent="test agent")
        cs = reader.source("some/path")

        # A factory function is set instead of the URL_READER, and
        # it constructs a URL_READER with user_agent passed in.
        url_reader = cs.url_reader
        self.assertNotEqual(URL_READER, url_reader)

        # Override the default URL_READER to track arguments being passed.
        simplestreams.mirrors.cs.URL_READER = fake_url_reader
        result = url_reader("a", "b", something="c")

        # It passes all the same arguments, with "user_agent" added in.
        self.assertEqual(
            {"user_agent": "test agent", "something": "c", "ARGS": ("a", "b")},
            result)

        # Restore default UrlReader.
        simplestreams.mirrors.cs.URL_READER = URL_READER

    def test_source_user_agent_no_trailing_slash(self):
        """
        When user_agent is set, it is passed to the ContentSource even
        if there is no trailing slash.
        """
        reader = UrlMirrorReader("/prefix", mirrors=["a/", "b/"],
                                 user_agent="test agent")
        cs = reader.source("some/path")

        # A factory function is set instead of the URL_READER, and
        # it constructs a URL_READER with user_agent passed in.
        url_reader = cs.url_reader
        self.assertNotEqual(URL_READER, url_reader)

        # Override the default URL_READER to track arguments being passed.
        simplestreams.mirrors.cs.URL_READER = fake_url_reader
        result = url_reader("a", "b", something="c")

        # It passes all the same arguments, with "user_agent" added in.
        self.assertEqual(
            {"user_agent": "test agent", "something": "c", "ARGS": ("a", "b")},
            result)

        # Restore default UrlReader.
        simplestreams.mirrors.cs.URL_READER = URL_READER

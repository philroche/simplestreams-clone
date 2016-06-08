from simplestreams.mirrors.glance import GlanceMirror

from unittest import TestCase


class FakeOpenstack(object):
    def load_keystone_creds(self):
        return {"auth_url": "http://keystone/api/"}

    def get_service_conn_info(self, url, region_name=None, auth_url=None):
        return {"endpoint": "http://objectstore/api/",
                "tenant_id": "bar456"}


class TestGlanceMirror(TestCase):
    """Tests for GlanceMirror methods."""

    def test_adapt_source_entry(self):
        """
        adapt_source_entry() creates a new dict based on passed-in dict
        with added properties for use in a local simplestreams index.
        """
        config = {"content_id": "foo123"}
        mirror = GlanceMirror(
            config, region="region1", openstack=FakeOpenstack())

        source_entry = {"source-key": "source-value"}
        # hypervisor_mapping = None
        output_entry = mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=None, image_name="foobuntu-X",
            image_md5_hash=None, image_size=None)

        # Source and output entry are different objects.
        self.assertNotEqual(source_entry, output_entry)

        # Output entry gets a few new properties like the endpoint and
        # owner_id taken from the GlanceMirror and  OpenStack configuration,
        # region from the value passed into GlanceMirror constructor, and
        # image name from the passed in value.
        # It also contains the source entries as well.
        self.assertEqual(
            {"endpoint": "http://keystone/api/",
             "name": "foobuntu-X",
             "owner_id": "bar456",
             "region": "region1",
             "source-key": "source-value"},
            output_entry)

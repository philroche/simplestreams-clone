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
        # Adapts source entry for use in a local simplestreams index.
        config = {"content_id": "foo123"}
        mirror = GlanceMirror(
            config, region="region1", openstack=FakeOpenstack())

        source_entry = {"source-key": "source-value"}
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

    def test_adapt_source_entry_ignored_properties(self):
        # adapt_source_entry() drops some properties from the source entry.
        config = {"content_id": "foo123"}
        mirror = GlanceMirror(
            config, region="region1", openstack=FakeOpenstack())
        source_entry = {"path": "foo",
                        "product_name": "bar",
                        "version_name": "baz",
                        "item_name": "bah"}
        output_entry = mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=None, image_name="foobuntu-X",
            image_md5_hash=None, image_size=None)

        # None of the values in 'source_entry' are preserved.
        for key in ("path", "product_name", "version_name", "item"):
            self.assertNotIn("path", output_entry)

    def test_adapt_source_entry_image_md5_and_size(self):
        # adapt_source_entry() will use passed in values for md5 and size.
        config = {"content_id": "foo123"}
        mirror = GlanceMirror(
            config, region="region1", openstack=FakeOpenstack())
        # Even old stale values will be overridden when image_md5_hash and
        # image_size are passed in.
        source_entry = {"md5": "stale-md5"}
        output_entry = mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=None, image_name="foobuntu-X",
            image_md5_hash="new-md5", image_size=5)

        self.assertEqual("new-md5", output_entry["md5"])
        self.assertEqual(5, output_entry["size"])

    def test_adapt_source_entry_image_md5_and_size_both_required(self):
        # adapt_source_entry() requires both md5 and size to not ignore them.
        config = {"content_id": "foo123"}
        mirror = GlanceMirror(
            config, region="region1", openstack=FakeOpenstack())
        # Even old stale values will be overridden when image_md5_hash and
        # image_size are passed in.
        source_entry = {"md5": "stale-md5"}

        # image_size is not passed in, so md5 value is not used either.
        output_entry1 = mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=None, image_name="foobuntu-X",
            image_md5_hash="new-md5", image_size=None)
        self.assertEqual("stale-md5", output_entry1["md5"])
        self.assertNotIn("size", output_entry1)

        # image_md5_hash is not passed in, so image_size is not used either.
        output_entry2 = mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=None, image_name="foobuntu-X",
            image_md5_hash=None, image_size=5)
        self.assertEqual("stale-md5", output_entry2["md5"])
        self.assertNotIn("size", output_entry2)

    def test_adapt_source_entry_hypervisor_mapping(self):
        # If hypervisor_mapping is set to True, 'virt' value is derived from
        # the source entry 'ftype'.
        config = {"content_id": "foo123"}
        mirror = GlanceMirror(
            config, region="region1", openstack=FakeOpenstack())
        source_entry = {"ftype": "disk1.img"}
        output_entry = mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=True, image_name="foobuntu-X",
            image_md5_hash=None, image_size=None)

        self.assertEqual("kvm", output_entry["virt"])

    def test_adapt_source_entry_hypervisor_mapping_ftype_required(self):
        # If hypervisor_mapping is set to True, but 'ftype' is missing in the
        # source entry, 'virt' value is not added to the returned entry.
        config = {"content_id": "foo123"}
        mirror = GlanceMirror(
            config, region="region1", openstack=FakeOpenstack())
        source_entry = {}
        output_entry = mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=True, image_name="foobuntu-X",
            image_md5_hash=None, image_size=None)

        self.assertNotIn("virt", output_entry)

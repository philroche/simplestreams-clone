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
            source_entry, hypervisor_mapping=False, image_name="foobuntu-X",
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
            source_entry, hypervisor_mapping=False, image_name="foobuntu-X",
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
            source_entry, hypervisor_mapping=False, image_name="foobuntu-X",
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
            source_entry, hypervisor_mapping=False, image_name="foobuntu-X",
            image_md5_hash="new-md5", image_size=None)
        self.assertEqual("stale-md5", output_entry1["md5"])
        self.assertNotIn("size", output_entry1)

        # image_md5_hash is not passed in, so image_size is not used either.
        output_entry2 = mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=False, image_name="foobuntu-X",
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

    def test_create_glance_properties(self):
        # Constructs glance properties to set on image during upload
        # based on source image metadata.
        config = {"content_id": "foo123"}
        mirror = GlanceMirror(
            config, region="region1", openstack=FakeOpenstack())

        source_entry = {
            # All of these are carried over and potentially re-named.
            "product_name": "foobuntu",
            "version_name": "X",
            "item_name": "disk1.img",
            "os": "ubuntu",
            "version": "16.04",
            # Other entries are ignored.
            "something-else": "ignored",
        }
        properties = mirror.create_glance_properties(
            "content-1", "source-1", source_entry, hypervisor_mapping=False)

        # Output properties contain content-id and source-content-id based
        # on the passed in parameters, and carry over (with changed keys
        # for "os" and "version") product_name, version_name, item_name and
        # os and version values from the source entry.
        self.assertEqual(
            {"content_id": "content-1",
             "source_content_id": "source-1",
             "product_name": "foobuntu",
             "version_name": "X",
             "item_name": "disk1.img",
             "os_distro": "ubuntu",
             "os_version": "16.04"},
            properties)

    def test_create_glance_properties_arch(self):
        # When 'arch' is present in the source entry, it is adapted and
        # returned inside 'architecture' field.
        config = {"content_id": "foo123"}
        mirror = GlanceMirror(
            config, region="region1", openstack=FakeOpenstack())

        source_entry = {
            "product_name": "foobuntu",
            "version_name": "X",
            "item_name": "disk1.img",
            "os": "ubuntu",
            "version": "16.04",
            "arch": "amd64",
        }
        properties = mirror.create_glance_properties(
            "content-1", "source-1", source_entry, hypervisor_mapping=False)
        self.assertEqual("x86_64", properties["architecture"])

    def test_create_glance_properties_hypervisor_mapping(self):
        # When hypervisor_mapping is requested and 'ftype' is present in
        # the image metadata, 'hypervisor_type' is added to returned
        # properties.
        config = {"content_id": "foo123"}
        mirror = GlanceMirror(
            config, region="region1", openstack=FakeOpenstack())

        source_entry = {
            "product_name": "foobuntu",
            "version_name": "X",
            "item_name": "disk1.img",
            "os": "ubuntu",
            "version": "16.04",
            "ftype": "root.tar.gz",
        }
        properties = mirror.create_glance_properties(
            "content-1", "source-1", source_entry, hypervisor_mapping=True)
        self.assertEqual("lxc", properties["hypervisor_type"])

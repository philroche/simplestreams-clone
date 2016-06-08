from simplestreams.contentsource import MemoryContentSource
from simplestreams.mirrors.glance import GlanceMirror
import simplestreams.util

import os
from unittest import TestCase


class FakeOpenstack(object):
    def load_keystone_creds(self):
        return {"auth_url": "http://keystone/api/"}

    def get_service_conn_info(self, url, region_name=None, auth_url=None):
        return {"endpoint": "http://objectstore/api/",
                "tenant_id": "bar456"}


class FakeImage(object):
    def __init__(self, identifier):
        self.id = identifier


class FakeImages(object):
    def __init__(self):
        self.create_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return FakeImage('image-%d' % len(self.create_calls))


class FakeGlanceClient(object):
    def __init__(self, *args):
        self.images = FakeImages()


class TestGlanceMirror(TestCase):
    """Tests for GlanceMirror methods."""

    def setUp(self):
        self.config = {"content_id": "foo123"}
        self.mirror = GlanceMirror(
            self.config, name_prefix="auto-sync/", region="region1",
            openstack=FakeOpenstack())

    def test_adapt_source_entry(self):
        # Adapts source entry for use in a local simplestreams index.
        source_entry = {"source-key": "source-value"}
        output_entry = self.mirror.adapt_source_entry(
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
        source_entry = {"path": "foo",
                        "product_name": "bar",
                        "version_name": "baz",
                        "item_name": "bah"}
        output_entry = self.mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=False, image_name="foobuntu-X",
            image_md5_hash=None, image_size=None)

        # None of the values in 'source_entry' are preserved.
        for key in ("path", "product_name", "version_name", "item"):
            self.assertNotIn("path", output_entry)

    def test_adapt_source_entry_image_md5_and_size(self):
        # adapt_source_entry() will use passed in values for md5 and size.
        # Even old stale values will be overridden when image_md5_hash and
        # image_size are passed in.
        source_entry = {"md5": "stale-md5"}
        output_entry = self.mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=False, image_name="foobuntu-X",
            image_md5_hash="new-md5", image_size=5)

        self.assertEqual("new-md5", output_entry["md5"])
        self.assertEqual(5, output_entry["size"])

    def test_adapt_source_entry_image_md5_and_size_both_required(self):
        # adapt_source_entry() requires both md5 and size to not ignore them.

        source_entry = {"md5": "stale-md5"}

        # image_size is not passed in, so md5 value is not used either.
        output_entry1 = self.mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=False, image_name="foobuntu-X",
            image_md5_hash="new-md5", image_size=None)
        self.assertEqual("stale-md5", output_entry1["md5"])
        self.assertNotIn("size", output_entry1)

        # image_md5_hash is not passed in, so image_size is not used either.
        output_entry2 = self.mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=False, image_name="foobuntu-X",
            image_md5_hash=None, image_size=5)
        self.assertEqual("stale-md5", output_entry2["md5"])
        self.assertNotIn("size", output_entry2)

    def test_adapt_source_entry_hypervisor_mapping(self):
        # If hypervisor_mapping is set to True, 'virt' value is derived from
        # the source entry 'ftype'.
        source_entry = {"ftype": "disk1.img"}
        output_entry = self.mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=True, image_name="foobuntu-X",
            image_md5_hash=None, image_size=None)

        self.assertEqual("kvm", output_entry["virt"])

    def test_adapt_source_entry_hypervisor_mapping_ftype_required(self):
        # If hypervisor_mapping is set to True, but 'ftype' is missing in the
        # source entry, 'virt' value is not added to the returned entry.
        source_entry = {}
        output_entry = self.mirror.adapt_source_entry(
            source_entry, hypervisor_mapping=True, image_name="foobuntu-X",
            image_md5_hash=None, image_size=None)

        self.assertNotIn("virt", output_entry)

    def test_create_glance_properties(self):
        # Constructs glance properties to set on image during upload
        # based on source image metadata.
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
        properties = self.mirror.create_glance_properties(
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
        source_entry = {
            "product_name": "foobuntu",
            "version_name": "X",
            "item_name": "disk1.img",
            "os": "ubuntu",
            "version": "16.04",
            "arch": "amd64",
        }
        properties = self.mirror.create_glance_properties(
            "content-1", "source-1", source_entry, hypervisor_mapping=False)
        self.assertEqual("x86_64", properties["architecture"])

    def test_create_glance_properties_hypervisor_mapping(self):
        # When hypervisor_mapping is requested and 'ftype' is present in
        # the image metadata, 'hypervisor_type' is added to returned
        # properties.
        source_entry = {
            "product_name": "foobuntu",
            "version_name": "X",
            "item_name": "disk1.img",
            "os": "ubuntu",
            "version": "16.04",
            "ftype": "root.tar.gz",
        }
        properties = self.mirror.create_glance_properties(
            "content-1", "source-1", source_entry, hypervisor_mapping=True)
        self.assertEqual("lxc", properties["hypervisor_type"])

    def test_prepare_glance_arguments(self):
        # Prepares arguments to pass to GlanceClient.images.create()
        # based on image metadata from the simplestreams source.
        source_entry = {}
        create_arguments = self.mirror.prepare_glance_arguments(
            "foobuntu-X", source_entry, image_md5_hash=None, image_size=None,
            image_properties=None)

        # Arguments to always pass in contain the image name, container format,
        # disk format, whether image is public, and any passed-in properties.
        self.assertEqual(
            {"name": "foobuntu-X",
             "container_format": 'bare',
             "disk_format": "qcow2",
             "is_public": True,
             "properties": None},
            create_arguments)

    def test_prepare_glance_arguments_disk_format(self):
        # Disk format is based on the image 'ftype' (if defined).
        source_entry = {"ftype": "root.tar.gz"}
        create_arguments = self.mirror.prepare_glance_arguments(
            "foobuntu-X", source_entry, image_md5_hash=None, image_size=None,
            image_properties=None)

        self.assertEqual("root-tar", create_arguments["disk_format"])

    def test_prepare_glance_arguments_size(self):
        # Size is read from image metadata if defined.
        source_entry = {"size": 5}
        create_arguments = self.mirror.prepare_glance_arguments(
            "foobuntu-X", source_entry, image_md5_hash=None, image_size=None,
            image_properties=None)

        self.assertEqual(5, create_arguments["size"])

    def test_prepare_glance_arguments_checksum(self):
        # Checksum is based on the source entry 'md5' value, if defined.
        source_entry = {"md5": "foo123"}
        create_arguments = self.mirror.prepare_glance_arguments(
            "foobuntu-X", source_entry, image_md5_hash=None, image_size=None,
            image_properties=None)

        self.assertEqual("foo123", create_arguments["checksum"])

    def test_prepare_glance_arguments_size_and_md5_override(self):
        # Size and md5 hash are overridden from the passed-in values even if
        # defined on the source entry.
        source_entry = {"size": 5, "md5": "foo123"}
        create_arguments = self.mirror.prepare_glance_arguments(
            "foobuntu-X", source_entry, image_md5_hash="bar456", image_size=10,
            image_properties=None)

        self.assertEqual(10, create_arguments["size"])
        self.assertEqual("bar456", create_arguments["checksum"])

    def test_prepare_glance_arguments_size_and_md5_no_override_hash(self):
        # If only one of image_md5_hash or image_size is passed directly in,
        # the other value is not overridden either.
        source_entry = {"size": 5, "md5": "foo123"}
        create_arguments = self.mirror.prepare_glance_arguments(
            "foobuntu-X", source_entry, image_md5_hash="bar456",
            image_size=None, image_properties=None)

        self.assertEqual(5, create_arguments["size"])
        self.assertEqual("foo123", create_arguments["checksum"])

    def test_prepare_glance_arguments_size_and_md5_no_override_size(self):
        # If only one of image_md5_hash or image_size is passed directly in,
        # the other value is not overridden either.
        source_entry = {"size": 5, "md5": "foo123"}
        create_arguments = self.mirror.prepare_glance_arguments(
            "foobuntu-X", source_entry, image_md5_hash=None, image_size=10,
            image_properties=None)

        self.assertEqual(5, create_arguments["size"])
        self.assertEqual("foo123", create_arguments["checksum"])

    def test_download_image(self):
        # Downloads image from a contentsource.
        content = "foo bazes the bar"
        content_source = MemoryContentSource(
            url="http://image-store/fooubuntu-X-disk1.img", content=content)
        image_metadata = {"pubname": "foobuntu-X", "size": 5}
        path, size, md5_hash = self.mirror.download_image(
            content_source, image_metadata)
        self.addCleanup(os.unlink, path)
        self.assertIsNotNone(path)
        self.assertIsNone(size)
        self.assertIsNone(md5_hash)

    def test_download_image_progress_callback(self):
        # Progress callback is called with image name, size, status and buffer
        # size after every 10kb of data: 3 times for 25kb of data below.
        content = "abcdefghij" * int(1024 * 2.5)
        content_source = MemoryContentSource(
            url="http://image-store/fooubuntu-X-disk1.img", content=content)
        image_metadata = {"pubname": "foobuntu-X", "size": len(content)}

        self.progress_calls = []

        def log_progress_calls(message):
            self.progress_calls.append(message)

        self.addCleanup(
            setattr, self.mirror, "progress_callback",
            self.mirror.progress_callback)
        self.mirror.progress_callback = log_progress_calls
        path, size, md5_hash = self.mirror.download_image(
            content_source, image_metadata)
        self.addCleanup(os.unlink, path)

        self.assertEqual(
            [{"name": "foobuntu-X", "size": 25600, "status": "Downloading",
              "written": 10240}] * 3,
            self.progress_calls)

    def test_download_image_error(self):
        # When there's an error during download, contentsource is still closed
        # and the error is propagated below.
        content = "abcdefghij"
        content_source = MemoryContentSource(
            url="http://image-store/fooubuntu-X-disk1.img", content=content)
        image_metadata = {"pubname": "foobuntu-X", "size": len(content)}

        # MemoryContentSource has an internal file descriptor which indicates
        # if close() method has been called on it.
        self.assertFalse(content_source.fd.closed)

        self.addCleanup(
            setattr, self.mirror, "progress_callback",
            self.mirror.progress_callback)
        self.mirror.progress_callback = lambda message: 1/0

        self.assertRaises(
            ZeroDivisionError,
            self.mirror.download_image, content_source, image_metadata)

        # We rely on the MemoryContentSource.close() side-effect to ensure
        # close() method has indeed been called on the passed-in ContentSource.
        self.assertTrue(content_source.fd.closed)

    def test_insert_item(self):
        # Downloads an image from a contentsource, uploads it into Glance,
        # adapting and munging as needed (it updates the keystone endpoint,
        # image and owner ids).
        # This test is basically an integration test to make sure all the
        # methods used by insert_item() are tied together in one good
        # fully functioning whole.

        # This is a real snippet from the simplestreams index entry for
        # Ubuntu 14.04 amd64 image from cloud-images.ubuntu.com as of
        # 2016-06-05.
        source_index = {
            u'content_id': u'com.ubuntu.cloud:released:download',
            u'datatype': u'image-downloads',
            u'format': u'products:1.0',
            u'license': (u'http://www.canonical.com/'
                         u'intellectual-property-policy'),
            u'products': {u'com.ubuntu.cloud:server:14.04:amd64': {
                u'aliases': u'14.04,default,lts,t,trusty',
                u'arch': u'amd64',
                u'os': u'ubuntu',
                u'release': u'trusty',
                u'release_codename': u'Trusty Tahr',
                u'release_title': u'14.04 LTS',
                u'support_eol': u'2019-04-17',
                u'supported': True,
                u'version': u'14.04',
                u'versions': {u'20160602': {
                    u'items': {u'disk1.img': {
                        u'ftype': u'disk1.img',
                        u'md5': u'e5436cd36ae6cc298f081bf0f6b413f1',
                        u'path': (
                            u'server/releases/trusty/release-20160602/'
                            u'ubuntu-14.04-server-cloudimg-amd64-disk1.img'),
                        u'sha256': (u'5b982d7d4dd1a03e88ae5f35f02ed44f'
                                    u'579e2711f3e0f27ea2bff20aef8c8d9e'),
                        u'size': 259850752}},
                    u'label': u'release',
                    u'pubname': u'ubuntu-trusty-14.04-amd64-server-20160602',
                }}}
            }
        }

        # "Pedigree" is basically a "path" to get to the image data in
        # simplestreams index, going through "products", their "versions",
        # and nested "items".
        pedigree = (
            u'com.ubuntu.cloud:server:14.04:amd64', u'20160602', u'disk1.img')
        product = source_index[u'products'][pedigree[0]]
        image_data = product[u'versions'][pedigree[1]][u'items'][pedigree[2]]

        content_source = MemoryContentSource(
            url="http://image-store/fooubuntu-X-disk1.img",
            content="image-data")

        # Use a fake GlanceClient to track arguments passed into
        # GlanceClient.images.create().
        self.addCleanup(setattr, self.mirror, "gclient", self.mirror.gclient)
        self.mirror.gclient = FakeGlanceClient()

        target = {
            'content_id': 'auto.sync',
            'datatype': 'image-ids',
            'format': 'products:1.0',
        }

        self.mirror.insert_item(
            image_data, source_index, target, pedigree, content_source)

        passed_create_kwargs = self.mirror.gclient.images.create_calls[0]

        # There is a 'data' argument pointing to an open file descriptor
        # for the locally downloaded image.
        self.assertIn("data", passed_create_kwargs)
        passed_create_kwargs.pop("data")

        expected_create_kwargs = {
            'name': ('auto-sync/'
                     'ubuntu-trusty-14.04-amd64-server-20160602-disk1.img'),
            'checksum': u'e5436cd36ae6cc298f081bf0f6b413f1',
            'disk_format': 'qcow2',
            'container_format': 'bare',
            'is_public': True,
            'properties': {
                'os_distro': u'ubuntu',
                'item_name': u'disk1.img',
                'os_version': u'14.04',
                'architecture': 'x86_64',
                'version_name': u'20160602',
                'content_id': 'auto.sync',
                'product_name': u'com.ubuntu.cloud:server:14.04:amd64',
                'source_content_id': u'com.ubuntu.cloud:released:download'},
            'size': '259850752'}
        self.assertEqual(
            expected_create_kwargs, passed_create_kwargs)

        # Almost real resulting data as produced by simplestreams before
        # insert_item refactoring to allow for finer-grained testing.
        expected_target_index = {
            'content_id': 'auto.sync',
            'datatype': 'image-ids',
            'format': 'products:1.0',
            'products': {
                "com.ubuntu.cloud:server:14.04:amd64": {
                    "aliases": "14.04,default,lts,t,trusty",
                    "arch": "amd64",
                    "label": "release",
                    "os": "ubuntu",
                    "owner_id": "bar456",
                    "pubname": "ubuntu-trusty-14.04-amd64-server-20160602",
                    "release": "trusty",
                    "release_codename": "Trusty Tahr",
                    "release_title": "14.04 LTS",
                    "support_eol": "2019-04-17",
                    "supported": "True",
                    "version": "14.04",
                    "versions": {"20160602": {"items": {"disk1.img": {
                        "endpoint": "http://keystone/api/",
                        "ftype": "disk1.img",
                        "id": "image-1",
                        "md5": "e5436cd36ae6cc298f081bf0f6b413f1",
                        "name": ("auto-sync/ubuntu-trusty-14.04-amd64-"
                                 "server-20160602-disk1.img"),
                        "region": "region1",
                        "sha256": ("5b982d7d4dd1a03e88ae5f35f02ed44f"
                                   "579e2711f3e0f27ea2bff20aef8c8d9e"),
                        "size": "259850752"
                    }}}}
                }
            }
        }

        # Apply the condensing as done in GlanceMirror.insert_products()
        # to ensure we compare with the desired resulting simplestreams data.
        sticky = ['ftype', 'md5', 'sha256', 'size', 'name', 'id', 'endpoint',
                  'region']
        simplestreams.util.products_condense(target, sticky)

        self.assertEqual(expected_target_index, target)

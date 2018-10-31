#   Copyright (C) 2013 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
#
#   Simplestreams is free software: you can redistribute it and/or modify it
#   under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Simplestreams is distributed in the hope that it will be useful, but
#   WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
#   or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public
#   License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Simplestreams.  If not, see <http://www.gnu.org/licenses/>.

import simplestreams.filters as filters
import simplestreams.mirrors as mirrors
import simplestreams.util as util
from simplestreams import checksum_util
import simplestreams.openstack as openstack
from simplestreams.log import LOG

import copy
import errno
import glanceclient
import json
import os
import re


def get_glanceclient(version='1', **kwargs):
    # newer versions of the glanceclient will do this 'strip_version' for
    # us, but older versions do not.
    kwargs['endpoint'] = _strip_version(kwargs['endpoint'])
    pt = ('endpoint', 'token', 'insecure', 'cacert')
    kskw = {k: kwargs.get(k) for k in pt if k in kwargs}
    if kwargs.get('session'):
        sess = kwargs.get('session')
        return glanceclient.Client(version, session=sess)
    else:
        return glanceclient.Client(version, **kskw)


def empty_iid_products(content_id):
    return {'content_id': content_id, 'products': {},
            'datatype': 'image-ids', 'format': 'products:1.0'}


def canonicalize_arch(arch):
    '''Canonicalize Ubuntu archs for use in OpenStack'''
    newarch = arch.lower()
    if newarch == "amd64":
        newarch = "x86_64"
    if newarch == "i386":
        newarch = "i686"
    if newarch == "ppc64el":
        newarch = "ppc64le"
    if newarch == "powerpc":
        newarch = "ppc"
    if newarch == "armhf":
        newarch = "armv7l"
    if newarch == "arm64":
        newarch = "aarch64"
    return newarch


LXC_FTYPES = {
    'root.tar.gz': 'root-tar',
    'root.tar.xz': 'root-tar',
    'squashfs': 'squashfs',
}

QEMU_FTYPES = {
    'disk.img': 'qcow2',
    'disk1.img': 'qcow2',
}


def disk_format(ftype):
    '''Canonicalize disk formats for use in OpenStack.
    Input ftype is a 'ftype' from a simplestream feed.
    Return value is the appropriate 'disk_format' for glance.'''
    newftype = ftype.lower()
    if newftype in LXC_FTYPES:
        return LXC_FTYPES[newftype]
    if newftype in QEMU_FTYPES:
        return QEMU_FTYPES[newftype]
    return None


def hypervisor_type(ftype):
    '''Determine hypervisor type based on image format'''
    newftype = ftype.lower()
    if newftype in LXC_FTYPES:
        return 'lxc'
    if newftype in QEMU_FTYPES:
        return 'qemu'
    return None


def virt_type(hypervisor_type):
    '''Map underlying hypervisor types into high level virt types'''
    newhtype = hypervisor_type.lower()
    if newhtype == 'qemu':
        return 'kvm'
    if newhtype == 'lxc':
        return 'lxd'
    return None


# glance mirror 'image-downloads' content into glance
# if provided an object store, it will produce a 'image-ids' mirror
class GlanceMirror(mirrors.BasicMirrorWriter):
    """
    GlanceMirror syncs external simplestreams index and images to Glance.

    `client` argument is used for testing to override openstack module:
    allows dependency injection of fake "openstack" module.
    """
    def __init__(self, config, objectstore=None, region=None,
                 name_prefix=None, progress_callback=None,
                 client=None):
        super(GlanceMirror, self).__init__(config=config)

        self.item_filters = self.config.get('item_filters', [])
        if len(self.item_filters) == 0:
            self.item_filters = ['ftype~(disk1.img|disk.img)',
                                 'arch~(x86_64|amd64|i386)']
        self.item_filters = filters.get_filters(self.item_filters)

        self.index_filters = self.config.get('index_filters', [])
        if len(self.index_filters) == 0:
            self.index_filters = ['datatype=image-downloads']
        self.index_filters = filters.get_filters(self.index_filters)

        self.loaded_content = {}
        self.store = objectstore

        if client is None:
            client = openstack

        self.keystone_creds = client.load_keystone_creds()

        self.name_prefix = name_prefix or ""
        if region is not None:
            self.keystone_creds['region_name'] = region

        self.progress_callback = progress_callback

        conn_info = client.get_service_conn_info(
            'image', **self.keystone_creds)
        self.glance_api_version = conn_info['glance_version']
        self.gclient = get_glanceclient(version=self.glance_api_version,
                                        **conn_info)
        self.tenant_id = conn_info['tenant_id']

        self.region = self.keystone_creds.get('region_name', 'nullregion')
        self.cloudname = config.get("cloud_name", 'nullcloud')
        self.crsn = '-'.join((self.cloudname, self.region,))
        self.auth_url = self.keystone_creds['auth_url']

        self.content_id = config.get("content_id")
        self.modify_hook = config.get("modify_hook")

        self.inserts = {}
        if not self.content_id:
            raise TypeError("content_id is required")

    def _cidpath(self, content_id):
        return "streams/v1/%s.json" % content_id

    def load_products(self, path=None, content_id=None):
        """
        Load metadata for all currently uploaded active images in Glance.

        Uses glance as the definitive store, but loads metadata from existing
        simplestreams indexes as well.
        """
        my_cid = self.content_id

        # glance is the definitive store.  Any data loaded from the store
        # is secondary.
        store_t = None
        if self.store:
            try:
                path = self._cidpath(my_cid)
                store_t = util.load_content(self.store.source(path).read())
            except IOError as e:
                if e.errno != errno.ENOENT:
                    raise
        if not store_t:
            store_t = empty_iid_products(my_cid)

        glance_t = empty_iid_products(my_cid)

        images = self.gclient.images.list()
        for image in images:
            if self.glance_api_version == "1":
                image = image.to_dict()
                props = image['properties']
            else:
                props = copy.deepcopy(image)

            if image['owner'] != self.tenant_id:
                continue

            if props.get('content_id') != my_cid:
                continue

            if image.get('status') != "active":
                LOG.warn("Ignoring inactive image %s with status '%s'" % (
                    image['id'], image.get('status')))
                continue

            source_content_id = props.get('source_content_id')

            product = props.get('product_name')
            version = props.get('version_name')
            item = props.get('item_name')
            if not (version and product and item and source_content_id):
                LOG.warn("%s missing required fields" % image['id'])
                continue

            # get data from the datastore for this item, if it exists
            # and then update that with glance data (just in case different)
            try:
                item_data = util.products_exdata(store_t,
                                                 (product, version, item,),
                                                 include_top=False,
                                                 insert_fieldnames=False)
            except KeyError:
                item_data = {}

            # If original simplestreams-metadata is stored on the image,
            # use that as well.
            if 'simplestreams_metadata' in props:
                simplestreams_metadata = json.loads(
                    props.get('simplestreams_metadata'))
            else:
                simplestreams_metadata = {}
            item_data.update(simplestreams_metadata)

            item_data.update({'name': image['name'], 'id': image['id']})
            if 'owner_id' not in item_data:
                item_data['owner_id'] = self.tenant_id

            util.products_set(glance_t, item_data,
                              (product, version, item,))

        for product in glance_t['products']:
            glance_t['products'][product]['region'] = self.region
            glance_t['products'][product]['endpoint'] = self.auth_url

        return glance_t

    def filter_item(self, data, src, target, pedigree):
        return filters.filter_item(self.item_filters, data, src, pedigree)

    def create_glance_properties(self, content_id, source_content_id,
                                 image_metadata, hypervisor_mapping):
        """
        Construct extra properties to store in Glance for an image.

        Based on source image metadata.
        """
        properties = {
            'content_id': content_id,
            'source_content_id': source_content_id,
        }
        # An iterator of properties to carry over: if a property needs
        # renaming, uses a tuple (old name, new name).
        carry_over_simple = (
            'product_name', 'version_name', 'item_name')
        carry_over = carry_over_simple + (
            ('os', 'os_distro'), ('version', 'os_version'))
        for carry_over_property in carry_over:
            if isinstance(carry_over_property, tuple):
                name_old, name_new = carry_over_property
            else:
                name_old = name_new = carry_over_property
            properties[name_new] = image_metadata.get(name_old)

        if 'arch' in image_metadata:
            properties['architecture'] = canonicalize_arch(
                image_metadata['arch'])

        if hypervisor_mapping and 'ftype' in image_metadata:
            _hypervisor_type = hypervisor_type(image_metadata['ftype'])
            if _hypervisor_type:
                properties['hypervisor_type'] = _hypervisor_type

        # Store flattened metadata for a source image along with the
        # image in 'simplestreams_metadata' property.
        simplestreams_metadata = image_metadata.copy()
        drop_keys = carry_over_simple + ('path',)
        for remove_key in drop_keys:
            if remove_key in simplestreams_metadata:
                del simplestreams_metadata[remove_key]
        properties['simplestreams_metadata'] = json.dumps(
            simplestreams_metadata, sort_keys=True)
        return properties

    def prepare_glance_arguments(self, full_image_name, image_metadata,
                                 image_md5_hash, image_size, image_properties):
        """
        Prepare arguments to pass into Glance image creation method.

        Uses `image_metadata` for source image to derive image size, md5 hash,
        disk format (based on 'ftype' field, if defined, otherwise defaults to
        'qcow2').

        If `image_md5_hash` and `image_size` are defined, overrides the
        values from image_metadata with their values.

        Sets extra image properties to dict `image_properties`.

        Returns a dict to use as keyword arguments passed directly to
        GlanceClient.images.create().
        """
        create_kwargs = {
            'name': full_image_name,
            'container_format': 'bare',
            'is_public': True,
            'properties': image_properties,
        }

        # In v2 is_public=True is visibility='public'
        if self.glance_api_version == "2":
            del create_kwargs['is_public']
            create_kwargs['visibility'] = 'public'

        # v2 automatically calculates size and checksum
        if self.glance_api_version == "1":
            if 'size' in image_metadata:
                create_kwargs['size'] = int(image_metadata.get('size'))
            if 'md5' in image_metadata:
                create_kwargs['checksum'] = image_metadata.get('md5')
            if image_md5_hash and image_size:
                create_kwargs.update({
                    'checksum': image_md5_hash,
                    'size': image_size,
                })

        if 'ftype' in image_metadata:
            create_kwargs['disk_format'] = (
                disk_format(image_metadata['ftype']) or 'qcow2'
            )
        else:
            create_kwargs['disk_format'] = 'qcow2'

        return create_kwargs

    def download_image(self, contentsource, image_stream_data):
        """
        Download an image from contentsource.

        `image_stream_data` represents a flattened image metadata structure
        to use for any logging messages.

        Returns a tuple of
           (str(local-image-path), int(image-size), str(image-md5-hash)).
        """
        image_name = image_stream_data.get('pubname')
        image_size = image_stream_data.get('size')

        if self.progress_callback:
            def progress_wrapper(written):
                self.progress_callback(
                    dict(status="Downloading", name=image_name,
                         size=None if image_size is None else int(image_size),
                         written=written))
        else:
            def progress_wrapper(written):
                pass

        try:
            tmp_path, _ = util.get_local_copy(
                contentsource, progress_callback=progress_wrapper)

            if self.modify_hook:
                (new_size, new_md5) = call_hook(
                    item=image_stream_data, path=tmp_path,
                    cmd=self.modify_hook)
            else:
                new_size = os.path.getsize(tmp_path)
                new_md5 = image_stream_data.get('md5')
        finally:
            contentsource.close()

        return tmp_path, new_size, new_md5

    def adapt_source_entry(self, source_entry, hypervisor_mapping, image_name,
                           image_md5_hash, image_size):
        """
        Adapts the source simplestreams dict `source_entry` for use in the
        generated local simplestreams index.
        """
        output_entry = source_entry.copy()

        # Drop attributes not needed for the simplestreams index itself.
        for property_name in ('path', 'product_name', 'version_name',
                              'item_name'):
            if property_name in output_entry:
                del output_entry[property_name]

        if hypervisor_mapping and 'ftype' in output_entry:
            _hypervisor_type = hypervisor_type(output_entry['ftype'])
            if _hypervisor_type:
                _virt_type = virt_type(_hypervisor_type)
                if _virt_type:
                    output_entry['virt'] = _virt_type

        output_entry['region'] = self.region
        output_entry['endpoint'] = self.auth_url
        output_entry['owner_id'] = self.tenant_id

        output_entry['name'] = image_name
        if image_md5_hash and image_size:
            output_entry['md5'] = image_md5_hash
            output_entry['size'] = str(image_size)

        return output_entry

    def _insert_item(self, data, src, target, pedigree, contentsource):
        """
        Upload image into glance and add image metadata to simplestreams index.

        `data` is the metadata for a particular image file from the source:
            unused since all that data is present in the `src` entry for
            the corresponding image as well.
        `src` contains the entire simplestreams index from the image syncing
            source.
        `target` is the simplestreams index for currently available images
            in glance (generated by load_products()) to add this item to.
        `pedigree` is a "path" to get to the `data` for the image we desire,
            a tuple of (product_name, version_name, image_type).
        `contentsource` is a ContentSource to download the actual image data
            from.
        """
        # Extract and flatten metadata for a product image matching
        #   (product-name, version-name, image-type)
        # from the tuple `pedigree` in the source simplestreams index.
        flattened_img_data = util.products_exdata(
            src, pedigree, include_top=False)

        tmp_path = None

        full_image_name = "{}{}".format(
            self.name_prefix,
            flattened_img_data.get('pubname', flattened_img_data.get('name')))
        if not full_image_name.endswith(flattened_img_data['item_name']):
            full_image_name += "-{}".format(flattened_img_data['item_name'])

        # Download images locally into a temporary file.
        tmp_path, new_size, new_md5 = self.download_image(
            contentsource, flattened_img_data)

        hypervisor_mapping = self.config.get('hypervisor_mapping', False)

        glance_props = self.create_glance_properties(
            target['content_id'], src['content_id'], flattened_img_data,
            hypervisor_mapping)
        create_kwargs = self.prepare_glance_arguments(
            full_image_name, flattened_img_data, new_md5, new_size,
            glance_props)

        target_sstream_item = self.adapt_source_entry(
            flattened_img_data, hypervisor_mapping, full_image_name, new_md5,
            new_size)

        try:
            if self.glance_api_version == "1":
                # Set data as string if v1
                create_kwargs['data'] = open(tmp_path, 'rb')
            else:
                # Keep properties for v2 update call
                _properties = create_kwargs['properties']
                del create_kwargs['properties']

            glance_image = self.gclient.images.create(**create_kwargs)
            target_sstream_item['id'] = glance_image.id

            if self.glance_api_version == "2":
                # Upload for v2
                self.gclient.images.upload(glance_image.id,
                                           open(tmp_path, 'rb'))
                # Update properties for v2
                self.gclient.images.update(glance_image.id, **_properties)

            # Validate the image checksum and size. This will throw an
            # IOError if they do not match.
            self.validate_image(glance_image.id, new_md5, new_size)

            print("created %s: %s" % (glance_image.id, full_image_name))

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        util.products_set(target, target_sstream_item, pedigree)
        # We can safely ignore path and content arguments since they are
        # unused in insert_products below.
        self.insert_products(None, target, None)

    def validate_image(self, image_id, checksum, size, delete=True):
        """Validate an image's checksum and size after upload.

        Check for expected checksum and size.
        Throw an IOError if they do not match.

        :param image_id: str Glance Image ID
        :param checksum: str Expected MD5 sum of the image
        :param size: int Expected size in bytes of the image
        :returns: None
        """
        if not isinstance(size, util.INTEGER_TYPES):
            raise TypeError("size '%s' is not an integer" % str(size))
        found = self.gclient.images.get(image_id)
        if found.size == size and found.checksum == checksum:
            return
        msg = (
            ("Invalid glance image: %s. " % image_id) +
            ("Expected size=%s md5=%s. Found size=%s md5=%s." %
             (size, checksum, found.size, found.checksum)))
        if delete:
            LOG.warning("Deleting image %s: %s", image_id, msg)
            self.gclient.images.delete(image_id)
        raise IOError(msg)

    def insert_item(self, data, src, target, pedigree, contentsource):
        """Queue item to be inserted in subsequent call to insert_version

        This adds the item to self.inserts which is then handled in
        insert_version.  That allows the code to have context on
        all the items for a given version, and "choose" one.  Ie,
        if both root.tar.xz and squashfs are available, preference
        can be given to the root.tar.gz.
        """

        product_name, version_name, item_name = pedigree
        if product_name not in self.inserts:
            self.inserts[product_name] = {}
        if version_name not in self.inserts[product_name]:
            self.inserts[product_name][version_name] = {}

        if 'ftype' in data:
            ftype = data['ftype']
        else:
            flat = util.products_exdata(src, pedigree, include_top=False)
            ftype = flat.get('ftype')
        self.inserts[product_name][version_name][item_name] = (
            ftype, (data, src, target, pedigree, contentsource))

    def insert_version(self, data, src, target, pedigree):
        """Upload all images for this version into glance
        and add image metadata to simplestreams index.

        All the work actually happens in _insert_item.
        """

        product_name, version_name = pedigree
        inserts = self.inserts.get(product_name, {}).get(version_name, [])

        rtar_names = [f for f in inserts
                      if inserts[f][0] in ('root.tar.gz', 'root.tar.xz')]

        for _iname, (ftype, iargs) in inserts.items():
            if ftype == "squashfs" and rtar_names:
                LOG.info("[%s] Skipping ftype 'squashfs' image in preference"
                         "for root tarball type in %s",
                         '/'.join(pedigree), rtar_names)
                continue
            self._insert_item(*iargs)

        # we do not specifically do anything for insert_version, but
        # call parent.
        super(GlanceMirror, self).insert_version(data, src, target, pedigree)

    def remove_item(self, data, src, target, pedigree):
        util.products_del(target, pedigree)
        if 'id' in data:
            print("removing %s: %s" % (data['id'], data['name']))
            self.gclient.images.delete(data['id'])

    def filter_index_entry(self, data, src, pedigree):
        return filters.filter_dict(self.index_filters, data)

    def insert_products(self, path, target, content):
        if not self.store:
            return

        tree = copy.deepcopy(target)
        util.products_prune(tree, preserve_empty_products=True)

        # stop these items from copying up when we call condense
        sticky = ['ftype', 'md5', 'sha256', 'size', 'name', 'id']

        # LP: #1329805. Juju expects these on the item.
        if self.config.get('sticky_endpoint_region', True):
            sticky += ['endpoint', 'region']

        util.products_condense(tree, sticky=sticky)

        tsnow = util.timestamp()
        tree['updated'] = tsnow

        dpath = self._cidpath(tree['content_id'])
        LOG.info("writing data: %s", dpath)
        self.store.insert_content(dpath, util.dump_data(tree))

        # now insert or update an index
        ipath = "streams/v1/index.json"
        try:
            index = util.load_content(self.store.source(ipath).read())
        except IOError as exc:
            if exc.errno != errno.ENOENT:
                raise
            index = {"index": {}, 'format': 'index:1.0',
                     'updated': util.timestamp()}

        index['index'][tree['content_id']] = {
            'updated': tsnow,
            'datatype': 'image-ids',
            'clouds': [{'region': self.region, 'endpoint': self.auth_url}],
            'cloudname': self.cloudname,
            'path': dpath,
            'products': list(tree['products'].keys()),
            'format': tree['format'],
        }
        LOG.info("writing data: %s", ipath)
        self.store.insert_content(ipath, util.dump_data(index))


class ItemInfoDryRunMirror(GlanceMirror):
    def __init__(self, config, objectstore):
        super(ItemInfoDryRunMirror, self).__init__(config, objectstore)
        self.items = {}

    def noop(*args):
        pass

    insert_index = noop
    insert_index_entry = noop
    insert_products = noop
    insert_product = noop
    insert_version = noop
    remove_item = noop
    remove_product = noop
    remove_version = noop

    def insert_item(self, data, src, target, pedigree, contentsource):
        data = util.products_exdata(src, pedigree)
        if 'size' in data and 'path' in data and 'pubname' in data:
            self.items[data['pubname']] = int(data['size'])


def _checksum_file(fobj, read_size=util.READ_SIZE, checksums=None):
    if checksums is None:
        checksums = {'md5': None}
    cksum = checksum_util.checksummer(checksums=checksums)
    while True:
        buf = fobj.read(read_size)
        cksum.update(buf)
        if len(buf) != read_size:
            break
    return cksum.hexdigest()


def call_hook(item, path, cmd):
    env = os.environ.copy()
    env.update(item)
    env['IMAGE_PATH'] = path
    env['FIELDS'] = ' '.join(item.keys()) + ' IMAGE_PATH'

    util.subp(cmd, env=env, capture=False)

    with open(path, "rb") as fp:
        md5 = _checksum_file(fp, checksums={'md5': None})

    return (os.path.getsize(path), md5)


def _strip_version(endpoint):
    """Strip a version from the last component of an endpoint if present"""

    # Get rid of trailing '/' if present
    if endpoint.endswith('/'):
        endpoint = endpoint[:-1]
    url_bits = endpoint.split('/')
    # regex to match 'v1' or 'v2.0' etc
    if re.match(r'v\d+\.?\d*', url_bits[-1]):
        endpoint = '/'.join(url_bits[:-1])
    return endpoint

# vi: ts=4 expandtab syntax=python

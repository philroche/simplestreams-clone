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
import simplestreams.openstack as openstack
from simplestreams.log import LOG

import copy
import errno
import glanceclient
import os


def get_glanceclient(version='1', **kwargs):
    pt = ('endpoint', 'token', 'insecure', 'cacert')
    kskw = {k: kwargs.get(k) for k in pt if k in kwargs}
    return glanceclient.Client(version, **kskw)


def empty_iid_products(content_id):
    return {'content_id': content_id, 'products': {},
            'datatype': 'image-ids', 'format': 'products:1.0'}


# glance mirror 'image-downloads' content into glance
# if provided an object store, it will produce a 'image-ids' mirror
class GlanceMirror(mirrors.BasicMirrorWriter):
    def __init__(self, config, objectstore=None, region=None,
                 name_prefix=None):
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

        self.keystone_creds = openstack.load_keystone_creds()

        self.name_prefix = name_prefix or ""
        if region is not None:
            self.keystone_creds['region_name'] = region

        conn_info = openstack.get_service_conn_info('image',
                                                    **self.keystone_creds)
        self.gclient = get_glanceclient(**conn_info)
        self.tenant_id = conn_info['tenant_id']

        self.region = self.keystone_creds.get('region_name', 'nullregion')
        self.cloudname = config.get("cloud_name", 'nullcloud')
        self.crsn = '-'.join((self.cloudname, self.region,))
        self.auth_url = self.keystone_creds['auth_url']

        self.content_id = config.get("content_id")
        self.modify_hook = config.get("modify_hook")

        if not self.content_id:
            raise TypeError("content_id is required")

    def _cidpath(self, content_id):
        return "streams/v1/%s.json" % content_id

    def load_products(self, path=None, content_id=None):
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
            image = image.to_dict()

            if image['owner'] != self.tenant_id:
                continue

            props = image['properties']
            if props.get('content_id') != my_cid:
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

    def insert_item(self, data, src, target, pedigree, contentsource):
        flat = util.products_exdata(src, pedigree, include_top=False)

        tmp_path = None
        tmp_del = None

        name = flat.get('pubname', flat.get('name'))
        if not name.endswith(flat['item_name']):
            name += "-%s" % (flat['item_name'])

        t_item = flat.copy()
        if 'path' in t_item:
            del t_item['path']

        props = {'content_id': target['content_id'],
                 'source_content_id': src['content_id']}
        for n in ('product_name', 'version_name', 'item_name'):
            props[n] = flat[n]
            del t_item[n]

        arch = flat.get('arch')
        if arch:
            t_item['arch'] = arch
            if arch == "amd64":
                arch = "x86_64"
            props['architecture'] = arch

        fullname = self.name_prefix + name
        create_kwargs = {
            'name': fullname,
            'properties': props,
            'disk_format': 'qcow2',
            'container_format': 'bare',
            'is_public': True,
        }
        if 'size' in data:
            create_kwargs['size'] = data.get('size')

        if 'md5' in data:
            create_kwargs['checksum'] = data.get('md5')

        try:
            try:
                (tmp_path, tmp_del) = util.get_local_copy(contentsource)
                if self.modify_hook:
                    (newsize, newmd5) = call_hook(item=t_item, path=tmp_path,
                                                  cmd=self.modify_hook)
                    create_kwargs['checksum'] = newmd5
                    create_kwargs['size'] = newsize
                    t_item['md5'] = newmd5
                    t_item['size'] = newsize

            finally:
                contentsource.close()

            create_kwargs['data'] = open(tmp_path, 'rb')
            ret = self.gclient.images.create(**create_kwargs)
            t_item['id'] = ret.id
            print("created %s: %s" % (ret.id, fullname))

        finally:
            if tmp_del and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        t_item['region'] = self.region
        t_item['endpoint'] = self.auth_url
        t_item['owner_id'] = self.tenant_id
        t_item['name'] = fullname
        util.products_set(target, t_item, pedigree)

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
        util.products_prune(tree)
        # stop these items from copying up when we call condense
        sticky = ['ftype', 'md5', 'sha256', 'size', 'name', 'id']
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


def _checksum_file(fobj, read_size=util.READ_SIZE, checksums=None):
    if checksums is None:
        checksums = {'md5': None}
    cksum = util.checksummer(checksums=checksums)
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

# vi: ts=4 expandtab syntax=python

#!/usr/bin/python

import simplestreams.mirrors as mirrors
import simplestreams.util as util
import simplestreams.openstack as openstack
from simplestreams.log import LOG

import copy
import errno
import glanceclient
import os
import re


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
                store_t = util.load_content(self.store.reader(path).read())
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
        flat = util.products_exdata(src, pedigree, include_top=False)
        return (flat.get('ftype') in ('disk1.img', 'disk.img') and
                flat.get('arch') in ('x86_64', 'amd64', 'i386'))

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
        if arch == "amd64":
            arch = "x86_64"
        if arch:
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
        return data.get('datatype') in ("image-downloads", None)

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
            index = util.load_content(self.store.reader(ipath).read())
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

# vi: ts=4 expandtab syntax=python

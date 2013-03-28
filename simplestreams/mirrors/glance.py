#!/usr/bin/python

import simplestreams.mirrors as mirrors
import simplestreams.util as util
import simplestreams.openstack as openstack

import copy
import errno
import glanceclient
import os
import re


def get_glanceclient(version='1', **kwargs):
    pt = ('endpoint', 'token', 'insecure', 'cacert')
    kskw = {k: kwargs.get(k) for k in pt if k in kwargs}
    return glanceclient.Client(version, **kskw)


def translate_dl_content_id(content_id, cloudname):
    # given content_id=com.ubuntu.cloud:released:download
    # return "com.ubuntu.cloud:released:%s" % cloudname
    toks = content_id.split(":")
    return ":".join(toks[:-1]) + ":" + cloudname


def empty_iid_products(content_id):
    return {'content_id': content_id, 'products': {},
            'datatype': 'image-ids'}


# glance mirror 'image-downloads' content into glance
# if provided an object store, it will produce a 'image-ids' mirror
class GlanceMirror(mirrors.BasicMirrorWriter):
    def __init__(self, config, objectstore=None):
        super(GlanceMirror, self).__init__(config=config)

        self.loaded_content = {}
        self.store = objectstore

        self.keystone_creds = openstack.load_keystone_creds()
        conn_info = openstack.get_service_conn_info('image',
		                                    **self.keystone_creds)
        self.gclient = get_glanceclient(**conn_info)
        self.tenant_id = conn_info['tenant_id']
        self.cloudname = "foocloud"

    def _cidpath(self, content_id):
        return "streams/v1/%s.js" % content_id

    def load_products(self, path=None, content_id=None):
        my_cid = translate_dl_content_id(content_id, self.cloudname)

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

            product = props.get('product_name')
            version = props.get('version_name')
            item = props.get('item_name')
            if not (version and product and item):
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

            util.products_set(glance_t, item_data,
                (product, version, item,))

        print util.dump_data(glance_t)
        return glance_t 

    def filter_item(self, data, src, target, pedigree):
        return data.get('ftype') in ('disk1.img', 'disk.img')

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
        
        props = {'content_id': target['content_id']}
        for n in ('product_name', 'version_name', 'item_name'):
            props[n] = flat[n]
            del t_item[n]

        create_kwargs = {
            'name': name,
            'properties': props,
            'disk_format': 'qcow2',
            'container_format': 'bare',
        }
        if 'size' in data:
            create_kwargs['size'] = data.get('size')

        if 'md5' in data:
            create_kwargs['checksum'] = data.get('md5')
        
        try:
            try:
                (tmp_path, tmp_del) = util.get_local_copy(contentsource.read)
            finally:
                contentsource.close()

            create_kwargs['data'] = open(tmp_path, 'rb')
            ret = self.gclient.images.create(**create_kwargs)
            t_item['id'] = ret.id
            print "created %s: %s" % (ret.id, name)

        finally:
            if tmp_del and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        util.products_set(target, t_item, pedigree)

    def remove_item(self, data, src, target, pedigree):
        util.products_del(target, pedigree)
        if 'id' in data:
            self.gclient.images.delete(data['id'])

    def filter_index_entry(self, data, src, pedigree):
        return data.get('datatype') in ("image-downloads", None)

    def insert_products(self, path, target, content):
        if self.store:
            tree = copy.deepcopy(target)
            util.products_prune(tree)
            #util.products_condense(tree)
            
            dpath = self._cidpath(tree['content_id'])
            self.store.insert_content(dpath, util.dump_data(tree))

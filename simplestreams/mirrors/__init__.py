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

import errno

import simplestreams.util as util
import simplestreams.contentsource as cs
from simplestreams.log import LOG


class MirrorReader(object):
    def load_products(self, path):
        content = self.reader(path).read()
        return util.load_content(content)

    def reader(self, path):
        raise NotImplementedError()


class MirrorWriter(object):
    def load_products(self, path=None, content_id=None):
        raise NotImplementedError()

    def sync_products(self, reader, path=None, products=None, content=None):
        # reader:   a Reader for opening files referenced in products
        # path:     the path of where to store this.
        #           if path is None, do not store the products file itself
        # products: a products file in products:1.0 format
        # content:  a rendered products tree, allowing you to store
        #           externally signed content.
        #
        # One of content, path, or products is required.
        #  * if path is not given, no rendering of products tree will be stored
        #  * if content is None, it will be loaded from reader(path).read()
        #    or rendered (json.dumps(products)) from products.
        #  * if products is None, it will be loaded from content
        raise NotImplementedError()

    def sync_index(self, reader, path=None, src=None, content=None):
        # reader:   a Reader for opening files referenced in index or products
        #           files
        # path:     the path of where to store this.
        #           if path is None, do not store the index file itself
        # src:      a dictionary in index:1.0 format
        # content:  a rendered products tree, allowing you to store
        #           externally signed content.
        #
        # One of content, path, or products is required.
        #  * if path not given, no rendering of products tree will be stored
        #  * if content is None, it will be loaded from reader(path).read()
        #    or rendered (json.dumps(products)) from products.
        #  * if products is None, it will be loaded from content
        raise NotImplementedError()

    def sync(self, reader, path):
        content = reader(path).read()
        (payload, _sig) = util.read_possibly_signed(path, reader)
        data = util.load_content(payload)
        fmt = data.get("format", "UNSPECIFIED")
        if fmt == "products:1.0":
            return self.sync_products(reader, path, data, content)
        elif fmt == "index:1.0":
            return self.sync_index(reader, path, data, content)
        else:
            raise TypeError("Unknown format '%s' in '%s'" % (fmt, path))

    ## Index Operations ##
    def filter_index_entry(self, data, src, pedigree):
        # src is source index tree.
        # data is src['index'][ped[0]]
        return True

    def insert_index(self, path, src, content):
        # src is the source index tree
        # content is None or a json rendering (possibly signed) of src
        pass

    def insert_index_entry(self, data, src, pedigree, contentsource):
        # src is the top level index (index:1.0 format)
        # data is src['index'][pedigree[0]]
        # contentsource is a ContentSource if 'path' exists in data or None
        pass

    ## Products Operations ##
    def filter_product(self, data, src, target, pedigree):
        # src and target are top level products:1.0
        # data is src['products'][ped[0]]
        return True

    def filter_version(self, data, src, target, pedigree):
        # src and target are top level products:1.0
        # data is src['products'][ped[0]]['versions'][ped[1]]
        return True

    def filter_item(self, data, src, target, pedigree):
        # src and target are top level products:1.0
        # data is src['products'][ped[0]]['versions'][ped[1]]['items'][ped[2]]
        return True

    def insert_products(self, path, target, content):
        # path is the path to store data (where it came from on source mirror)
        # target is the target products:1.0 tree
        # content is None or a json rendering (possibly signed) of src
        pass

    def insert_product(self, data, src, target, pedigree):
        # src and target are top level products:1.0
        # data is src['products'][ped[0]]
        pass

    def insert_version(self, data, src, target, pedigree):
        # src and target are top level products:1.0
        # data is src['products'][ped[0]]['versions'][ped[1]]
        pass

    def insert_item(self, data, src, target, pedigree, contentsource):
        # src and target are top level products:1.0
        # data is src['products'][ped[0]]['versions'][ped[1]]['items'][ped[2]]
        # contentsource is a ContentSource if 'path' exists in data or None
        pass

    def remove_product(self, data, src, target, pedigree):
        # src and target are top level products:1.0
        # data is src['products'][ped[0]]
        pass

    def remove_version(self, data, src, target, pedigree):
        # src and target are top level products:1.0
        # data is src['products'][ped[0]]['versions'][ped[1]]
        pass

    def remove_item(self, data, src, target, pedigree):
        # src and target are top level products:1.0
        # data is src['products'][ped[0]]['versions'][ped[1]]['items'][ped[2]]
        pass


class UrlMirrorReader(MirrorReader):
    def __init__(self, prefix, mirrors=None):
        self._cs = cs.UrlContentSource
        if mirrors is None:
            mirrors = []
        self.mirrors = mirrors
        self.prefix = prefix

    def reader(self, path):
        mirrors = [m + path for m in self.mirrors]
        return self._cs(self.prefix + path, mirrors=mirrors)


class ObjectStoreMirrorReader(MirrorReader):
    def __init__(self, objectstore):
        self.objectstore = objectstore

    def reader(self, path):
        return self.objectstore.reader(path)


class BasicMirrorWriter(MirrorWriter):
    def __init__(self, config=None):
        super(BasicMirrorWriter, self).__init__()
        if config is None:
            config = {}
        self.config = config

    def sync_index(self, reader, path=None, src=None, content=None):
        (src, content) = _get_data_content(path, src, content, reader)

        util.expand_tree(src)

        check_tree_paths(src)

        itree = src.get('index')
        for content_id, index_entry in itree.items():
            if not self.filter_index_entry(index_entry, src, (content_id,)):
                continue
            epath = index_entry.get('path', None)
            mycs = None
            if epath:
                if index_entry.get('format') in ("index:1.0", "products:1.0"):
                    self.sync(reader, path=epath)
                mycs = reader(epath)

            self.insert_index_entry(index_entry, src, (content_id,), mycs)

        self.insert_index(path, src, content)

    def sync_products(self, reader, path=None, src=None, content=None):
        (src, content) = _get_data_content(path, src, content, reader)

        util.expand_tree(src)

        check_tree_paths(src)

        content_id = src['content_id']
        target = self.load_products(path, content_id)
        if not target:
            target = util.stringitems(src)

        util.expand_tree(target)

        stree = src.get('products', {})
        if 'products' not in target:
            target['products'] = {}

        tproducts = target['products']

        filtered_products = []
        prodname = None
        for prodname, product in stree.items():
            if not self.filter_product(product, src, target, (prodname,)):
                filtered_products.append(prodname)
                continue

            if prodname not in tproducts:
                tproducts[prodname] = util.stringitems(product)
            tproduct = tproducts[prodname]
            if 'versions' not in tproduct:
                tproduct['versions'] = {}

            src_filtered_items = []

            def _filter(itemkey):
                ret = self.filter_version(product['versions'][itemkey],
                                          src, target, (prodname, itemkey))
                if not ret:
                    src_filtered_items.append(itemkey)
                return ret

            (to_add, to_remove) = util.resolve_work(
                src=list(product.get('versions', {}).keys()),
                target=list(tproduct.get('versions', {}).keys()),
                maxnum=self.config.get('max_items'),
                keep=self.config.get('keep_items'), itemfilter=_filter)

            LOG.info("%s/%s: to_add=%s to_remove=%s", content_id, prodname,
                     to_add, to_remove)

            tversions = tproduct['versions']
            for vername in to_add:
                version = product['versions'][vername]

                if vername not in tversions:
                    tversions[vername] = util.stringitems(version)

                for itemname, item in version.get('items', {}).items():
                    pgree = (prodname, vername, itemname)
                    if not self.filter_item(item, src, target, pgree):
                        continue

                    ipath = item.get('path', None)
                    ipath_cs = None
                    if ipath:
                        ipath_cs = reader(ipath)
                    self.insert_item(item, src, target, pgree, ipath_cs)

                self.insert_version(version, src, target, (prodname, vername))

            if self.config.get('delete_filtered_items', False):
                for v in src_filtered_items:
                    if v not in to_remove and v in tversions:
                        to_remove.append(v)

            for vername in to_remove:
                tversion = tversions[vername]
                for itemname in list(tversion.get('items', {}).keys()):
                    self.remove_item(tversion['items'][itemname], src, target,
                                     (prodname, vername, itemname))

                self.remove_version(tversion, src, target, (prodname, vername))
                del tversions[vername]

            self.insert_product(tproduct, src, target, (prodname,))

        ## FIXME: below will remove products if they're in target
        ## (result of load_products) but not in the source products.
        ## that could accidentally delete a lot.
        ##
        del_products = []
        if self.config.get('delete_products', False):
            del_products.extend([p for p in list(tproducts.keys())
                                 if p not in stree])
        if self.config.get('delete_filtered_products', False):
            del_products.extend([p for p in filtered_products
                                 if p not in stree])

        for prodname in del_products:
            ## FIXME: we remove a product here, but unless that acts
            ## recursively, nothing will remove the items in that product
            self.remove_product(tproducts[prodname], src, target, (prodname,))
            del tproducts[prodname]

        self.insert_products(path, target, content)


# ObjectStoreMirrorWriter stores data in <prefix>/.data/<content_id>
class ObjectStoreMirrorWriter(BasicMirrorWriter):
    def __init__(self, config, objectstore):
        super(ObjectStoreMirrorWriter, self).__init__(config=config)
        self.store = objectstore

    def products_data_path(self, content_id):
        return ".data/%s" % content_id

    def load_products(self, path=None, content_id=None):
        if content_id:
            try:
                dpath = self.products_data_path(content_id)
                return util.load_content(self.reader(dpath).read())
            except IOError as e:
                if e.errno != errno.ENOENT:
                    raise

        if path:
            try:
                (payload, _sig) = util.read_possibly_signed(path, self.reader)
            except IOError as e:
                if e.errno != errno.ENOENT:
                    raise
                payload = "{}"

            return util.load_content(payload)
        raise TypeError("unable to load_products with no path")

    def reader(self, path):
        return self.store.reader(path)

    def insert_item(self, data, src, target, pedigree, contentsource):
        util.products_set(target, data, pedigree)
        if 'path' not in data:
            return
        if not self.config.get('item_download', True):
            return
        LOG.debug("inserting %s to %s", contentsource.url, data['path'])
        self.store.insert(data['path'], contentsource,
                          checksums=util.item_checksums(data), mutable=False)

    def insert_index_entry(self, data, src, pedigree, contentsource):
        epath = data.get('path', None)
        if not epath:
            return
        self.store.insert(epath, contentsource,
                          checksums=util.item_checksums(data))

    def insert_products(self, path, target, content):
        dpath = self.products_data_path(target['content_id'])
        self.store.insert_content(dpath, util.dump_data(target))
        if not path:
            return
        if not content:
            content = util.dump_data(target)
        self.store.insert_content(path, content)

    def insert_index(self, path, src, content):
        if not path:
            return
        if not content:
            content = util.dump_data(src)
        self.store.insert_content(path, content)

    def remove_item(self, data, src, target, pedigree):
        util.products_del(target, pedigree)
        if 'path' not in data:
            return
        self.store.remove(data['path'])


def _get_data_content(path, data, content, reader):
    if content is None and path:
        content = reader(path).read()
    if data is None and content:
        data = util.load_content(content)

    if not data:
        raise ValueError("Data could not be loaded. "
                         "Path or content is required")
    return (data, content)


def check_tree_paths(tree, fmt=None):
    if fmt is None:
        fmt = tree.get('format')
    if fmt == "products:1.0":
        def check_path(item, tree, pedigree):
            _pylint = (tree, pedigree)
            util.assert_safe_path(item.get('path'))
        util.walk_products(tree, cb_item=check_path)
    elif fmt == "index:1.0":
        index = tree.get('index')
        for content_id in index:
            util.assert_safe_path(index[content_id].get('path'))


# vi: ts=4 expandtab

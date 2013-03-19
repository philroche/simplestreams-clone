import errno

import simplestreams.util as util
import simplestreams.contentsource as cs


class MirrorReader(object):
    def load_products(self, path):
        content = self.reader(path).read()
        return util.load_content(content)

    def reader(self, path):
        raise NotImplementedError()


class MirrorWriter(object):
    def load_products(self, path=None):
        raise NotImplementedError()

    def sync_products(self, reader, path=None, products=None,
                      content=None):
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

    def sync_index(self, reader, path=None, index=None, content=None):
        # reader:   a Reader for opening files referenced in index or products
        #           files
        # path:     the path of where to store this.
        #           if path is None, do not store the index file itself
        # products: a products file in products:1.0 format
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

    def filter_index_entry(self, content_id, content, tree, pedigree):
        return True

    def filter_product(self, product_id, product, tree, pedigree):
        return True

    def filter_version(self, version_id, version, tree, pedigree):
        return True

    def filter_item(self, item_id, item, tree, pedigree):
        return True

    def insert_index(self, path, index, content):
        pass

    def insert_index_entry(self, contentsource, content_id, content, tree,
                           pedigree):
        pass

    def insert_products(self, path, products, content):
        pass

    def insert_product(self, product_id, product, tree, pedigree):
        pass

    def insert_version(self, version_id, version, tree, pedigree):
        pass

    def insert_item(self, contentsource, item_id, item, tree, pedigree):
        pass

    def remove_product(self, product_id, product, tree, pedigree):
        pass

    def remove_version(self, version_id, version, tree, pedigree):
        pass

    def remove_item(self, contentsource, item_id, item, tree, pedigree):
        pass


class UrlMirrorReader(MirrorReader):
    def __init__(self, prefix):
        self._cs = cs.UrlContentSource
        self.prefix = prefix

    def reader(self, path):
        return self._cs(self.prefix + path)


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

    def sync_index(self, reader, path=None, index=None, content=None):
        (index, content) = _get_data_content(path, index, content, reader)

        util.expand_tree(index)

        itree = index.get('index')
        for content_id, index_entry in itree.iteritems():
            if not self.filter_index_entry(content_id, index_entry, index,
                                           (content_id)):
                continue
            epath = index_entry.get('path', None)
            epath_cs = None
            if epath:
                if index_entry.get('format') in ("index:1.0", "products:1.0"):
                    self.sync(reader, path=epath)
                epath_cs = reader(epath)

            self.insert_index_entry(epath_cs, content_id, index_entry, index,
                                    (content_id,))

        self.insert_index(path, index, content)

    def sync_products(self, reader, path=None, products=None, content=None):
        (products, content) = _get_data_content(path, products, content,
                                                reader)

        util.expand_tree(products)

        tproducts = self.load_products(path)
        if not tproducts:
            tproducts = util.stringitems(products)

        util.expand_tree(tproducts)

        stree = products.get('products', {})
        if 'products' not in tproducts:
            tproducts['products'] = {}

        ttree = tproducts['products']

        filtered_products = []
        for prodname, product in stree.iteritems():
            if not self.filter_product(prodname, product, products,
                                       (prodname,)):
                filtered_products.append(prodname)
                continue

            if prodname not in ttree:
                ttree[prodname] = util.stringitems(product)
            tproduct = ttree[prodname]
            if 'versions' not in tproduct:
                tproduct['versions'] = {}

            src_filtered_items = []

            def _filter(itemkey):
                ret = self.filter_version(itemkey,
                                          product['versions'][itemkey],
                                          products, (prodname, itemkey))
                if not ret:
                    src_filtered_items.append(itemkey)
                return ret

            (to_add, to_remove) = util.resolve_work(
                src=product.get('versions', {}).keys(),
                target=tproduct.get('versions', {}).keys(),
                max=self.config.get('max_items'),
                keep=self.config.get('keep_items'), filter=_filter)

            print "%s: to_add=%s, to_del=%s" % (prodname, to_add, to_remove)

            tversions = tproduct['versions']
            for vername in to_add:
                version = product['versions'][vername]

                if vername not in tversions:
                    tversions[vername] = util.stringitems(version)

                added = {}
                for itemname, item in version.get('items', {}).iteritems():
                    pgree = (prodname, vername, itemname)
                    if not self.filter_item(itemname, item, products, pgree):
                        continue

                    ipath = item.get('path', None)
                    ipath_cs = None
                    if ipath:
                        ipath_cs = reader(ipath)
                    self.insert_item(ipath_cs, itemname, item, products, pgree)

                    added[itemname] = item

                self.insert_version(vername, version, products,
                                    (prodname, vername))

                tversions[vername]['items'] = added

            if self.config.get('delete_filtered_items', False):
                for v in src_filtered_items:
                    if v not in to_remove and v in tversions:
                        to_remove.append(v)

            for vername in to_remove:
                tversion = tversions[vername]
                for itemname in tversion.get('items', {}).keys():
                    self.remove_item(itemname, tversions[itemname],
                                     (prodname, vername, itemname))
                    del tversion[itemname]

                self.remove_version(vername, tversion, tproducts,
                                    (prodname, vername))
                del tversions[vername]

            self.insert_product(prodname, tproduct, tproducts, (prodname,))

        ## FIXME: below will remove products if they're in target
        ## (result of load_products) but not in the source products.
        ## that could accidentally delete a lot.
        ##
        del_products = []
        if self.config.get('delete_products', False):
            del_products.extend([p for p in ttree.keys() if p not in stree])
        if self.config.get('delete_filtered_products', False):
            del_products.extend([p for p in filtered_products
                                 if p not in stree])

        for prodname in del_products:
            ## FIXME: we remove a product here, but unless that acts
            ## recursively, nothing will remove the items in that product
            self.remove_product(prodname, ttree[prodname], tproducts,
                                (prodname,))
            del ttree[prodname]

        self.insert_products(path, tproducts, content)


class ObjectStoreMirrorWriter(BasicMirrorWriter):
    def __init__(self, config, objectstore):
        super(ObjectStoreMirrorWriter, self).__init__(config=config)
        self.store = objectstore

    def load_products(self, path=None):
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

    def insert_item(self, cs, itemname, item, products, pedigree):
        if 'path' not in item:
            return
        self.store.insert(item['path'], cs,
                          checksums=util.item_checksums(item), mutable=False)

    def insert_index_entry(self, cs, content_id, content, tree, pedigree):
        epath = content.get('path', None)
        if not epath:
            return
        self.store.insert(epath, cs, checksums=util.item_checksums(content))

    def insert_products(self, path, products, content):
        if not path:
            return
        if not content:
            content = util.dump_data(products)
        self.store.insert_content(path, content)

    def insert_index(self, path, index, content):
        if not path:
            return
        if not content:
            content = util.dump_data(index)
        self.store.insert_content(path, content)


def _get_data_content(path, data, content, reader):
    if content is None and path:
        content = reader(path).read()
    if data is None and content:
        data = util.load_content(content)

    if not data:
        raise ValueError("Data could not be loaded. "
                         "Path or content is required")
    return (data, content)


# vi: ts=4 expandtab

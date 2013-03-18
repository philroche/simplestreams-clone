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

    def sync_index(self, reader, path=None, index=None,content=None):
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
    def __init__(self, config):
        super(BasicMirrorWriter, self).__init__()
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

        ptree = products.get('products', {})
        for prodname, product in ptree.iteritems():
            if not self.filter_product(prodname, product, products,
                                       (prodname,)):
                continue

            for vername, version in product.get('versions', {}).iteritems():
                if not self.filter_version(vername, version, products,
                                           (prodname, vername)):
                    continue

                for itemname, item in version.get('items', {}).iteritems():
                    pgree = (prodname, vername, itemname)
                    if not self.filter_item(itemname, item, products, pgree):
                        continue

                    ipath = item.get('path', None)
                    ipath_cs = None
                    if ipath:
                        ipath_cs = reader(ipath)
                    self.insert_item(ipath_cs, itemname, item, products, pgree)

                self.insert_version(vername, version, products,
                                    (prodname, vername))

            self.insert_product(prodname, product, products, (prodname,))

        self.insert_products(path, products, content)


class ObjectStoreMirrorWriter(BasicMirrorWriter):
    def __init__(self, config, objectstore):
        super(ObjectStoreMirrorWriter, self).__init__(config=config)
        self.store = objectstore

    def load_products(self, path=None):
        if path:
            content = self.reader(path).read()
            return util.load_content(content)
        raise TypeError("unable to with no path")

    def reader(self, path):
        return self.store.reader(path)

    def insert_item(self, cs, itemname, item, products, pedigree):
        if 'path' not in item:
            return
        print "inserting %s" % item['path']
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

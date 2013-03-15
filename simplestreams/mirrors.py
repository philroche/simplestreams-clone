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

    def filter_index_entry(self, entry):
        _x = entry
        return True

    def filter_product(self, product_data):
        (_name, _data) = product_data
        return True

    def filter_version(self, version_data, product_data):
        (_pname, _pdata) = product_data
        (_vname, _vdata) = version_data
        return True

    def filter_item(self, item, product_data, version_data):
        (_pname, _pdata) = product_data
        (_vname, _vdata) = version_data
        _x = item
        return True


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


class ObjectStoreMirrorWriter(MirrorWriter):
    def __init__(self, config, objectstore):
        self.store = objectstore
        self.config = config

    def load_products(self, path=None):
        if path:
            content = self.reader(path).read()
            return util.load_content(content)
        raise TypeError("unable to with no path")

    def reader(self, path):
        return self.store.reader(path)

    def sync_index(self, reader, path=None, index=None, content=None):
        (index, content) = _get_data_content(path, index, content, reader)

        util.expand_tree(index)

        itree = index.get('index')
        for entry in itree:
            if not self.filter_index_entry(entry):
                continue
            if 'path' in entry:
                epath = entry['path']
                if entry.get('format') in ("index:1.0", "products:1.0"):
                    self.sync(reader, path=epath)
                else:
                    self.store.insert(epath, reader(epath),
                                      checksums=util.item_checksums(entry))
        if path:
            if not content:
                content = util.dump_data(index)
            self.store.insert_content(path, content)

    def sync_products(self, reader, path=None, products=None, content=None):
        (products, content) = _get_data_content(path, products, content,
                                                reader)

        util.expand_tree(products)

        ptree = products.get('products', {})
        for pdata in ptree.iteritems():
            if not self.filter_product(product_data=pdata):
                continue
            #print " insert product %s" % pdata[0]

            product = pdata[1]
            for verdata in product.get('versions', {}).iteritems():
                if not self.filter_version(version_data=verdata,
                                           product_data=pdata):
                    continue

                #print "  insert version %s" % verdata[0]

                version = verdata[1]
                for item in version.get('items', []):
                    if not self.filter_item(item=item, product_data=pdata,
                                            version_data=verdata):
                        continue

                    print "   insert item %s" % item
                    if 'path' in item:
                        self.store.insert(item['path'], reader(item['path']),
                                          checksums=util.item_checksums(item),
                                          mutable=False)

        if path:
            if not content:
                content = util.dump_data(products)
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

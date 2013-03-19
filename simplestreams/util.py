import errno
import hashlib
import os
import subprocess
import time
import urlparse
import json

import simplestreams.contentsource as cs

ALIASNAME = "_aliases"

PGP_SIGNED_MESSAGE_HEADER = "-----BEGIN PGP SIGNED MESSAGE-----"
PGP_SIGNATURE_HEADER = "-----BEGIN PGP SIGNATURE-----"
PGP_SIGNATURE_FOOTER = "-----END PGP SIGNATURE-----"

_UNSET = object()
CHECKSUMS = ("md5", "sha256", "sha512")


def stringitems(data):
    return {k:v for k,v in data.iteritems() if
            isinstance(v, (unicode, str))}


def products_exdata(tree, pedigree):
    harchy = (("products", "product_name"),
              ("versions", "version_name"),
              ("items", "item_name"))

    exdata = {}
    if tree:
        exdata.update(stringitems(tree))
    clevel = tree
    for (n, key) in enumerate(pedigree):
        dictname, fieldname = harchy[n]
        clevel = clevel.get(dictname, {}).get(key, {})
        exdata.update(stringitems(clevel))
        exdata[fieldname] = key
    return exdata


def walk_products(tree, cb_product=None, cb_version=None, cb_item=None,
              ret_finished=_UNSET):
    # walk a product tree. callbacks are called with (item, tree, (pedigree))
    for prodname, proddata in tree['products'].iteritems():
        ped = [prodname]
        if cb_product:
            ret = cb_product(proddata, tree, (prodname,))
            if ret_finished != _UNSET and ret == ret_finished:
                return

        if not cb_version and not cb_item:
            continue

        for vername, verdata in proddata['versions'].iteritems():
            if cb_version:
                ret = cb_version(verdata, tree, (prodname, vername))
                if ret_finished != _UNSET and ret == ret_finished:
                    return

            if not cb_item:
                continue

            for itemname, itemdata in verdata['items'].iteritems():
                ret = cb_item(itemdata, tree, (prodname, vername, itemname))
                if ret_finished != _UNSET and ret == ret_finished:
                    return


def expand_tree(tree, refs=None, delete=False):
    if refs is None:
        refs = tree.get(ALIASNAME, None)
    expand_data(tree, refs, delete)


def expand_data(data, refs=None, delete=False):
    if isinstance(data, dict):
        if isinstance(refs, dict):
            for key in data.keys():
                if key == ALIASNAME:
                    continue
                ref = refs.get(key)
                if not ref:
                    continue
                value = data.get(key)
                if value and isinstance(value, (unicode, str)):
                    data.update(ref[value])
                    if delete:
                        del data[key]
        for key in data:
            expand_data(data[key], refs)
    elif isinstance(data, list):
        for item in data:
            expand_data(item, refs)


def resolve_work(src, target, max=None, keep=False, filter=None,
                 sort_reverse=True):
    # if more than max items are in src, only the most recent max will be
    # stored in target.  If keep is true, then the most recent max items
    # will be kept in target even if they are no longer in src.
    # if keep is false the number in target will never be greater than that
    # in src.
    add = []
    remove = []
    reverse = sort_reverse

    if max is None and keep:
        raise TypeError("max(%s) cannot be None if keep is True" % max)

    for item in sorted(src, reverse=reverse):
        if item in target:
            continue
        if filter is None or filter(item):
            add.append(item)

    for item in sorted(target, reverse=reverse):
        if item not in src:
            remove.append(item)

    if keep and len(remove):
        after_add = len(target) + len(add)
        while len(remove) and (max > (after_add - len(remove))):
            remove.pop(0)

    mtarget = sorted([f for f in target if f not in remove], reverse=reverse)

    while max is not None and (len(add) + len(mtarget) > max):
        if len(mtarget):
            remove.append(mtarget.pop())
            continue
        if len(add):
            add.pop()
            continue

    return(add, remove)


def read_possibly_signed(path, reader=open):
    content = ""

    with reader(path) as cfp:
        content = cfp.read()

    if content.startswith(PGP_SIGNED_MESSAGE_HEADER):
        # http://rfc-ref.org/RFC-TEXTS/2440/chapter7.html
        out = ""
        cmd = ["gpg", "--batch", "--verify", "-"]
        sp = subprocess.Popen(cmd, stderr=subprocess.STDOUT,
                              stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        (out, _err) = sp.communicate(content)
        if sp.returncode != 0:
            raise subprocess.CalledProcessError(sp.returncode, cmd, output=out)

        ret = {'body': '', 'signature': '', 'garbage': ''}
        lines = content.splitlines()
        i = 0
        for i in range(0, len(lines)):
            if lines[i] == PGP_SIGNED_MESSAGE_HEADER:
                mode = "header"
                continue
            elif mode == "header":
                if lines[i] != "":
                    mode = "body"
                continue
            elif lines[i] == PGP_SIGNATURE_HEADER:
                mode = "signature"
                continue
            elif lines[i] == PGP_SIGNATURE_FOOTER:
                mode = "garbage"
                continue

            # dash-escaped content in body
            if lines[i].startswith("- ") and mode == "body":
                ret[mode] += lines[i][2:] + "\n"
            else:
                ret[mode] += lines[i] + "\n"

        return(ret['body'], ret['signature'])
    else:
        return(content, None)


def load_content(content):
    return json.loads(content)


def dump_data(data):
    return json.dumps(data, indent=1)


def timestamp(ts=None):
    return time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(ts))


def item_checksums(item):
    return {k:item[k] for k in CHECKSUMS if k in item}


class checksummer(object):
    _hasher = None
    algorithm = None
    expected = None

    def __init__(self, checksums):
        # expects a dict of hashname/value
        if not checksums:
            self._hasher = None
            return
        for meth in CHECKSUMS:
            if meth in checksums and meth in hashlib.algorithms:
                self._hasher = hashlib.new(meth)
                self.algorithm = meth

        self.expected = checksums.get(self.algorithm, None)

        if not self._hasher:
            raise TypeError("Unable to find suitable hash algorithm")

    def update(self, data):
        if self._hasher is None:
            return
        self._hasher.update(data)

    def hexdigest(self):
        if self._hasher is None:
            return None
        return self._hasher.hexdigest()

    def check(self):
        return (self.expected is None or self.expected == self.hexdigest())


def pass_if_enoent(exc):
    try:
        raise exc
    except IOError as e:
        if e.errno == errno.ENOENT:
            return
    raise exc


def read_url(url):
    return cs.UrlContentSource(url).read()

def sync_product(src_product, src_mirror, target_product, target_mirror,
                 products_path=None, prodname=None, resolve_args=None):

    if resolve_args is None:
        resolve_args = {}

    if src_product is None and products_path and prodname:
        src_product = src_mirror.load_product(path, prodname)

    if not prodname:
        prodname = src_product['product']

    if target_product is None:
        target_product = target_mirror.load_product(products_path, prodname)

        tprodname = target_product.get('product')

    # get a hash of version: flattened so that we have it.
    flatdata = {}
    for vername, verdata in src_product['versions'].iteritems():
        extra = exdata(prodname=prodname, proddata=src_product, vername=vername,
                       verdata=verdata)
        extra.update(verdata)
        flatdata[vername] = extra
        
    def version_filter(version):
        data = src_product['versions'][version].copy()
        #data['version'] = version
        
        return target_mirror.filter_version(flatdata[version])

    (to_add, to_remove) = resolve_work(src_product['versions'].keys(),
                                       target_product['versions'].keys(),
                                       filter=version_filter,
                                       **resolve_args)

    for version in to_add:
        target_mirror.insert_version(src_product['versions'][version], src_mirror.reader)
        target_stream['versions'] = version

    for version in to_remove:
        target_mirror.remove_version(flatdata[version])
        del target_stream['versions'][version]

    target_mirror.store_product(products_path, product=target_product)

    return target_product


def sync_products(src_products, src_mirror, target_mirror, path=None,
                  resolve_args=None):

    src_content = None
    if src_products is None and path:
        (src_content, signature) = read_possibly_signed(path,
                                                        src_mirror.reader)
        src_products = load_content(src_content)

    def wrap_sync_product(product, exdata):
        fullproduct = exdata.copy()
        fullproduct.update(product)

        if not target_mirror.filter_product(fullproduct):
            return

        sync_product(product, src_mirror, target_product=None,
                     target_mirror=target_mirror, products_path=path,
                     prodname = fullproduct['product'],
                     resolve_args=resolve_args)

    walk_products(src_products, wrap_sync_product)

    if path is not None:
        # if path was provided, insert it into the target
        # if we've already read the src_content above, do not read again
        if src_content is None:
            with src_mirror.reader(path) as fp:
                src_content = fp.read()

    # FIXME: if we'd filtered src_collection we should store target_collection
    target_mirror.store_products(path, products=src_products,
                                content=src_content)


def normalize_url(url):
    parsed = urlparse.urlparse(url)
    if not parsed.scheme:
        orig = url
        if url.startswith("/"):
            url = "file://%s" % url
        elif os.path.exists(url):
            url = "file://%s" % os.path.abspath(url)
        else:
            raise TypeError("Could not convert %s to url", url)
        if os.path.isdir(orig):
            url += os.path.sep
    return url


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise
    return
# vi: ts=4 expandtab

from simplestreams import collection

import errno
import os
import requests
import subprocess
import urlparse
import yaml


PGP_SIGNED_MESSAGE_HEADER = "-----BEGIN PGP SIGNED MESSAGE-----"
PGP_SIGNATURE_HEADER = "-----BEGIN PGP SIGNATURE-----"
PGP_SIGNATURE_FOOTER = "-----END PGP SIGNATURE-----"


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
    return yaml.safe_load(content)


def pass_if_enoent(exc):
    try:
        raise exc
    except IOError as e:
        if e.errno == errno.ENOENT:
            return
    raise exc


def url_reader(url):
    return RequestsUrlReader(url)


def sync_stream_file(path, src_mirror, target_mirror, resolve_args=None):
    return sync_stream(src_stream=None, src_mirror=src_mirror,
                       target_stream=None, target_mirror=target_mirror,
                       path=path, resolve_args=resolve_args)

def sync_stream(src_stream, src_mirror, target_stream, target_mirror,
                path=None, resolve_args=None):

    if resolve_args is None:
        resolve_args = {}

    src_content = None

    if src_stream is None and path:
        src_stream = src_mirror.load_stream(path)

    if target_stream is None:
        if not path:
            raise TypeError("target_stream is none, but no path provided")
        # if target_stream was not provided
        target_stream = target_mirror.load_stream(path, src_stream)

        if target_stream.iqn != src_stream.iqn:
            raise TypeError("source content iqn (%s) != "
                            "mirrored content iqn (%s) at %s" %
                            (src_stream.iqn, target_stream.iqn, path))

    (to_add, to_remove) = resolve_work(src_stream.item_groups,
                                       target_stream.item_groups,
                                       filter=target_mirror.filter_group,
                                       **resolve_args)

    for item_group in to_add:
        target_mirror.insert_group(item_group, src_mirror.reader)
        target_stream.item_groups.append(item_group)

    for item_group in to_remove:
        target_mirror.remove_group(item_group)
        target_stream.item_groups.remove(item_group)

    if path is not None:
        # if path was provided, insert it into the target
        # if we've already read the src_content above, do not read again
        if src_content is None:
            with src_mirror.reader(path) as fp:
                src_content = fp.read()

    target_mirror.store_stream(path, stream=target_stream,
                               content=src_content)

    return target_stream

class RequestsUrlReader(object):
    def __init__(self, url, buflen=None):
        self.req = requests.get(url, stream=True)
        self.r_iter = None
        if buflen is None:
            buflen = 1024 * 1024
        self.buflen = buflen
        self.leftover = None
        self.consumed = False

        if self.req.status_code == requests.codes.NOT_FOUND:
            myerr = IOError("Unable to open %s" % url)
            myerr.errno = errno.ENOENT
            raise myerr

        ce = self.req.headers.get('content-encoding', '').lower()
        if 'gzip' in ce or 'deflate' in ce:
            self._read = self.read_compressed
        else:
            self._read = self.read_raw

    def read(self, size=None):
        return self._read(size)

    def read_compressed(self, size=None):
        if not self.r_iter:
            self.r_iter = self.req.iter_content(self.buflen)

        if self.consumed:
            return bytes()

        ret = bytes()

        if self.leftover is not None:
            if len(self.leftover) > size:
                ret = self.leftover[0:size]
                self.leftover = self.leftover[size:]
                return ret
            ret = self.leftover
            self.leftover = None

        size_end = (size is not None and size >= 0)

        while True:
            try:
                ret += self.r_iter.next()
                if not size_end:
                    next
                if len(ret) >= size:
                    self.leftover = ret[size:]
                    return ret[0:size]
            except StopIteration as e:
                self.consumed = True
                return ret

    def read_raw(self, size=None):
        return self.req.raw.read(size)


def sync_collection(src_collection, src_mirror, target_mirror, path=None,
                    resolve_args=None):

    src_content = None
    if src_collection is None and path:
        (src_content, signature) = read_possibly_signed(path,
                                                        src_mirror.reader)
        src_collection = collection.Collection(load_content(src_content))

    for item in src_collection.streams:
        if not target_mirror.filter_stream(item):
            continue
        sync_stream_file(item.get('path'), src_mirror, target_mirror,
                         resolve_args=resolve_args)

    if path is not None:
        # if path was provided, insert it into the target
        # if we've already read the src_content above, do not read again
        if src_content is None:
            with src_mirror.reader(path) as fp:
                src_content = fp.read()

    # FIXME: if we'd filtered src_collection we should store target_collection
    target_mirror.store_collection(path, collection=src_collection,
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

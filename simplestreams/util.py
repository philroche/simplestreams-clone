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
import os
import re
import subprocess
import tempfile
import time
import json

import simplestreams.contentsource as cs
import simplestreams.checksum_util as checksum_util
from simplestreams.log import LOG

ALIASNAME = "_aliases"

PGP_SIGNED_MESSAGE_HEADER = "-----BEGIN PGP SIGNED MESSAGE-----"
PGP_SIGNATURE_HEADER = "-----BEGIN PGP SIGNATURE-----"
PGP_SIGNATURE_FOOTER = "-----END PGP SIGNATURE-----"

_UNSET = object()

READ_SIZE = (1024 * 10)

PRODUCTS_TREE_DATA = (
    ("products", "product_name"),
    ("versions", "version_name"),
    ("items", "item_name"),
)
PRODUCTS_TREE_HIERARCHY = [_k[0] for _k in PRODUCTS_TREE_DATA]
_HAS_GPGV = None


class SignatureMissingException(Exception):
    pass


try:
    # python2
    _STRING_TYPES = (str, basestring, unicode)
except NameError:
    # python3
    _STRING_TYPES = (str,)


def stringitems(data):
    f = {}
    for k, v in data.items():
        if isinstance(v, _STRING_TYPES):
            f[k] = v
        elif isinstance(v, (int, float)):
            f[k] = str(v)
    return f


def products_exdata(tree, pedigree, include_top=True, insert_fieldnames=True):
    # given 'tree' and 'pedigree' return a 'flattened' dict that contains
    # entries for all attributes of this item those that apply to its pedigree
    harchy = PRODUCTS_TREE_DATA

    exdata = {}
    if include_top and tree:
        exdata.update(stringitems(tree))
    clevel = tree
    for (n, key) in enumerate(pedigree):
        dictname, fieldname = harchy[n]
        clevel = clevel.get(dictname, {}).get(key, {})
        exdata.update(stringitems(clevel))
        if insert_fieldnames:
            exdata[fieldname] = key
    return exdata


def products_set(tree, data, pedigree):
    harchy = PRODUCTS_TREE_HIERARCHY

    cur = tree

    for n in range(0, len(pedigree)):
        if harchy[n] not in cur:
            cur[harchy[n]] = {}
        cur = cur[harchy[n]]
        if n != (len(pedigree) - 1):
            if pedigree[n] not in cur:
                cur[pedigree[n]] = {}
            cur = cur[pedigree[n]]

    cur[pedigree[-1]] = data


def products_del(tree, pedigree):
    harchy = PRODUCTS_TREE_HIERARCHY
    cur = tree
    for n in range(0, len(pedigree)):
        if harchy[n] not in cur:
            return
        cur = cur[harchy[n]]

        if n == (len(pedigree) - 1):
            break

        if pedigree[n] not in cur:
            return

        cur = cur[pedigree[n]]

    if pedigree[-1] in cur:
        del cur[pedigree[-1]]


def products_prune(tree, preserve_empty_products=False):
    for prodname in list(tree.get('products', {}).keys()):
        keys = list(tree['products'][prodname].get('versions', {}).keys())
        for vername in keys:
            vtree = tree['products'][prodname]['versions'][vername]
            for itemname in list(vtree.get('items', {}).keys()):
                if not vtree['items'][itemname]:
                    del vtree['items'][itemname]

            if 'items' not in vtree or not vtree['items']:
                del tree['products'][prodname]['versions'][vername]

        if ('versions' not in tree['products'][prodname] or
                not tree['products'][prodname]['versions']):
            del tree['products'][prodname]

    if (not preserve_empty_products and 'products' in tree and
            not tree['products']):
        del tree['products']


def walk_products(tree, cb_product=None, cb_version=None, cb_item=None,
                  ret_finished=_UNSET):
    # walk a product tree. callbacks are called with (item, tree, (pedigree))
    for prodname, proddata in tree['products'].items():
        if cb_product:
            ret = cb_product(proddata, tree, (prodname,))
            if ret_finished != _UNSET and ret == ret_finished:
                return

        if (not cb_version and not cb_item) or 'versions' not in proddata:
            continue

        for vername, verdata in proddata['versions'].items():
            if cb_version:
                ret = cb_version(verdata, tree, (prodname, vername))
                if ret_finished != _UNSET and ret == ret_finished:
                    return

            if not cb_item or 'items' not in verdata:
                continue

            for itemname, itemdata in verdata['items'].items():
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
            for key in list(data.keys()):
                if key == ALIASNAME:
                    continue
                ref = refs.get(key)
                if not ref:
                    continue
                value = data.get(key)
                if value and isinstance(value, _STRING_TYPES):
                    data.update(ref[value])
                    if delete:
                        del data[key]
        for key in data:
            expand_data(data[key], refs)
    elif isinstance(data, list):
        for item in data:
            expand_data(item, refs)


def resolve_work(src, target, maxnum=None, keep=False, itemfilter=None,
                 sort_reverse=True):
    # if more than maxnum items are in src, only the most recent maxnum will be
    # stored in target.  If keep is true, then the most recent maxnum items
    # will be kept in target even if they are no longer in src.
    # if keep is false the number in target will never be greater than that
    # in src.
    add = []
    remove = []
    reverse = sort_reverse

    if maxnum is None and keep:
        raise TypeError("maxnum(%s) cannot be None if keep is True" % maxnum)

    if not (maxnum is None or isinstance(maxnum, int)):
        raise TypeError("maxnum(%s) must be integer or None" % maxnum)

    if not (keep is None or isinstance(keep, int)):
        raise TypeError("keep(%s) must be integer or None" % keep)

    # Ensure that all source items are passed through filters
    # In case the filters have changed from the last run
    for item in sorted(src, reverse=reverse):
        if itemfilter is None or itemfilter(item):
            if item not in target:
                add.append(item)

    for item in sorted(target, reverse=reverse):
        if item not in src:
            remove.append(item)

    if keep and len(remove):
        after_add = len(target) + len(add)
        while len(remove) and (maxnum > (after_add - len(remove))):
            remove.pop(0)

    mtarget = sorted([f for f in target + add if f not in remove],
                     reverse=reverse)
    if maxnum is not None and len(mtarget) > maxnum:
        for item in mtarget[maxnum:]:
            if item in target:
                remove.append(item)
            else:
                add.pop(add.index(item))
    remove = sorted(remove, reverse=bool(not reverse))
    return(add, remove)


def policy_read_signed(content, path, keyring=None):
    # convenience wrapper around 'read_signed' for use MirrorReader policy
    return read_signed(content=content, keyring=keyring)


def has_gpgv():
    global _HAS_GPGV
    if _HAS_GPGV is not None:
        return _HAS_GPGV

    if which('gpgv'):
        try:
            env = os.environ.copy()
            env['LANG'] = 'C'
            out, err = subp(["gpgv", "--help"], capture=True, env=env)
            _HAS_GPGV = 'gnupg' in out.lower() or 'gnupg' in err.lower()
        except subprocess.CalledProcessError:
            _HAS_GPGV = False
    else:
        _HAS_GPGV = False
    return _HAS_GPGV


def read_signed(content, keyring=None, checked=True):
    # ensure that content is signed by a key in keyring.
    # if no keyring given use default.
    if content.startswith(PGP_SIGNED_MESSAGE_HEADER):
        if checked and keyring and has_gpgv():
            cmd = ["gpgv", "--keyring=%s" % keyring, "-"]
        elif checked:
            # http://rfc-ref.org/RFC-TEXTS/2440/chapter7.html
            cmd = ["gpg", "--batch", "--verify"]
            if keyring:
                cmd.append("--keyring=%s" % keyring)
            cmd.append("-")
        if checked:
            try:
                subp(cmd, data=content)
            except subprocess.CalledProcessError as e:
                LOG.debug("failed: %s\n out=%s\n err=%s" %
                          (' '.join(cmd), e.output[0], e.output[1]))
                raise e

        ret = {'body': [], 'signature': [], 'garbage': []}
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
                ret[mode].append(lines[i][2:])
            else:
                ret[mode].append(lines[i])

        ret['body'].append('')  # need empty line at end
        return "\n".join(ret['body'])
    else:
        raise SignatureMissingException("No signature found!")


def load_content(content):
    if isinstance(content, bytes):
        content = content.decode('utf-8')
    return json.loads(content)


def dump_data(data):
    return json.dumps(data, indent=1, sort_keys=True,
                      separators=(',', ': ')).encode('utf-8')


def timestamp(ts=None):
    return time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(ts))


def move_dups(src, target, sticky=None):
    # given src = {e1: {a:a, b:c}, e2: {a:a, b:d, e:f}}
    # update target with {a:a}, and delete 'a' from entries in dict1
    # if a key exists in target, it will not be copied or deleted.
    if len(src) == 0:
        return

    candidates = set.intersection(*[set(e.keys()) for e in src.values()])
    if sticky is not None:
        candidates.difference_update(sticky)

    updates = {}
    for entry in list(src.keys()):
        for k, v in src[entry].items():
            if k not in candidates:
                continue
            if k in updates:
                if v != updates[k] or not isinstance(v, _STRING_TYPES):
                    del updates[k]
                    candidates.remove(k)
            else:
                if isinstance(v, _STRING_TYPES) and target.get(k, v) == v:
                    updates[k] = v
                else:
                    candidates.remove(k)

    for entry in list(src.keys()):
        for k in list(src[entry].keys()):
            if k in updates:
                del src[entry][k]

    target.update(updates)


def products_condense(ptree, sticky=None, top='versions'):
    # walk a products tree, copying up item keys as far as they'll go
    # only move items to a sibling of the 'top'.

    if top not in ('versions', 'products'):
        raise ValueError("'top' must be one of: %s" %
                         ','.join(PRODUCTS_TREE_HIERARCHY))

    def call_move_dups(cur, _tree, pedigree):
        (_mtype, stname) = (("product", "versions"),
                            ("version", "items"))[len(pedigree) - 1]
        move_dups(cur.get(stname, {}), cur, sticky=sticky)

    walk_products(ptree, cb_version=call_move_dups)
    walk_products(ptree, cb_product=call_move_dups)
    if top == 'versions':
        return
    move_dups(ptree['products'], ptree)


def assert_safe_path(path):
    if path == "" or path is None:
        return
    path = str(path)
    if os.path.isabs(path):
        raise TypeError("Path '%s' is absolute path" % path)
    bad = (".." + os.path.sep, "..." + os.path.sep)
    for tok in bad:
        if path.startswith(tok):
            raise TypeError("Path '%s' starts with '%s'" % (path, tok))
    bad = (os.path.sep + ".." + os.path.sep, os.path.sep + "..." + os.path.sep)
    for tok in bad:
        if tok in path:
            raise TypeError("Path '%s' contains '%s'" % (path, tok))


def read_url(url):
    return cs.UrlContentSource(url).read()


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise
    return


def get_local_copy(contentsource, read_size=READ_SIZE, progress_callback=None):
    (tfd, tpath) = tempfile.mkstemp()
    tfile = os.fdopen(tfd, "wb")
    try:
        LOG.debug("getting local copy of %s", contentsource.url)
        while True:
            buf = contentsource.read(read_size)
            if progress_callback:
                progress_callback(read_size)
            tfile.write(buf)
            if len(buf) != read_size:
                break
        return (tpath, True)

    except Exception as e:
        os.unlink(tpath)
        raise e


def subp(args, data=None, capture=True, shell=False, env=None):
    if not capture:
        stdout, stderr = (None, None)
    else:
        stdout, stderr = (subprocess.PIPE, subprocess.PIPE)

    sp = subprocess.Popen(args, stdout=stdout, stderr=stderr,
                          stdin=subprocess.PIPE, shell=shell, env=env)
    if isinstance(data, str):
        data = data.encode('utf-8')

    (out, err) = sp.communicate(data)
    if isinstance(out, bytes):
        out = out.decode('utf-8')
    if isinstance(err, bytes):
        err = err.decode('utf-8')

    rc = sp.returncode
    if rc != 0:
        raise subprocess.CalledProcessError(rc, args, output=(out, err))

    return (out, err)


def get_sign_cmd(path, output=None, inline=False):
    cmd = ['gpg']
    defkey = os.environ.get('SS_GPG_DEFAULT_KEY')
    if defkey:
        cmd.extend(['--default-key', defkey])

    batch = os.environ.get('SS_GPG_BATCH', "1").lower()
    if batch not in ("0", "false"):
        cmd.append('--batch')

    if output:
        cmd.extend(['--output', output])

    if inline:
        cmd.append('--clearsign')
    else:
        cmd.extend(['--armor', '--detach-sign'])

    cmd.extend([path])
    return cmd


def make_signed_content_paths(content):
    # loads json content.  If it is a products:1.0 file
    # then it fixes up 'path' elements to point to signed names (.sjson)
    # returns tuple of (changed, updated)
    data = json.loads(content)

    if data.get("format") != "index:1.0":
        return (False, None)

    for content_ent in list(data.get('index', {}).values()):
        path = content_ent.get('path')
        if path.endswith(".json"):
            content_ent['path'] = signed_fname(path, inline=True)

    return (True, json.dumps(data, indent=1))


def signed_fname(fname, inline=True):
    if inline:
        sfname = fname[0:-len(".json")] + ".sjson"
    else:
        sfname = fname + ".gpg"

    return sfname


def rm_f_file(fname, skip=None):
    if skip is None:
        skip = []
    if fname in skip:
        return
    try:
        os.unlink(fname)
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            raise


def which(program):
    # Return path of program for execution if found in path
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    _fpath, _ = os.path.split(program)
    if _fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ.get("PATH", "").split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


def sign_file(fname, inline=True, outfile=None):
    if outfile is None:
        outfile = signed_fname(fname, inline=inline)
    rm_f_file(outfile, skip=["-"])
    return subp(get_sign_cmd(path=fname, output=outfile, inline=inline))[0]


def sign_content(content, outfile="-", inline=True):
    rm_f_file(outfile, skip=["-"])
    return subp(args=get_sign_cmd(path="-", output=outfile, inline=inline),
                data=content)[0]


def path_from_mirror_url(mirror, path):
    if path is not None:
        return (mirror, path)

    path_regex = "streams/v1/.*[.](sjson|json)$"
    result = re.search(path_regex, mirror)
    if result:
        path = mirror[result.start():]
        mirror = mirror[:result.start()]
    else:
        path = "streams/v1/index.sjson"

    return (mirror, path)


class ProgressAggregator(object):
    def __init__(self, remaining_items=None):
        self.last_emitted = 0
        self.current_written = 0
        self.current_file = None
        self.remaining_items = remaining_items
        if self.remaining_items:
            self.total_image_count = len(self.remaining_items)
            self.total_size = sum(self.remaining_items.values())
        else:
            self.total_image_count = 0
            self.total_size = 0
        self.total_written = 0

    def progress_callback(self, progress):
        if self.current_file != progress['name']:
            if self.remaining_items and self.current_file is not None:
                del self.remaining_items[self.current_file]
            self.current_file = progress['name']
            self.last_emitted = 0
            self.current_written = 0

        size = float(progress['size'])
        written = float(progress['written'])
        self.current_written += written
        self.total_written += written
        interval = self.current_written - self.last_emitted
        if interval > size / 100:
            self.last_emitted = self.current_written
            progress['written'] = self.current_written
            self.emit(progress)

    def emit(self, progress):
        raise NotImplementedError()


# these are legacy
CHECKSUMS = checksum_util.CHECKSUMS
item_checksums = checksum_util.item_checksums
ALGORITHMS = checksum_util.ALGORITHMS
checksummer = checksum_util.checksummer


# vi: ts=4 expandtab

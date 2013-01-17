import contextlib
import errno
import os
import subprocess
import stream
import urllib2
import yaml


PGP_SIGNED_MESSAGE_HEADER = "-----BEGIN PGP SIGNED MESSAGE-----"
PGP_SIGNATURE_HEADER = "-----BEGIN PGP SIGNATURE-----"
PGP_SIGNATURE_FOOTER = "-----END PGP SIGNATURE-----"


def resolve_work(src, target, max=None, keep=None, sort_reverse=True):
    add = []
    remove = []
    reverse = sort_reverse

    if keep is not None and max is not None and max > keep:
        raise TypeError("max: %s larger than keep: %s" % (max, keep))

    for item in sorted(src, reverse=reverse):
        if item not in target:
            add.append(item)

    for item in sorted(target, reverse=reverse):
        if item not in src:
            remove.append(item)

    if keep is not None and len(remove):
        after_add = len(target) + len(add)
        while len(remove) and keep > (after_add - len(remove)):
            remove.pop(0)

    final_count = (len(add) + len(target) - len(remove))
    if max is not None and final_count >= max:
        for i in range(0, final_count - max):
            add.pop()

    final_count = (len(add) + len(target) - len(remove))
    if max is not None and final_count > max:
        after_rem = sorted(list(set(target) - set(remove)), reverse=reverse)
        remove.append(after_rem[:-(final_count - max)])

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
            raise CalledProcessError(retcode, cmd, output=out)

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

def url_reader(url):
    try:
        return contextlib.closing(urllib2.urlopen(url))
    except urllib2.HTTPError as e:
        if e.code == 404:
            myerr = IOError(e.message)
            myerr.errno = errno.ENOENT
            raise myerr
        raise e
    except urllib2.URLError as e:
        if isinstance(e.reason, OSError):
            myerr = IOError(e.reason.message)
            myerr.errno = errno.ENOENT
            raise myerr
        raise e


def sync_stream_file(path, src_mirror, target_mirror, **kwargs):
    (src_content, signature) = read_possibly_signed(path, src_mirror.reader)
    src_stream = stream.Stream(load_content(src_content))

    try:
        (content, signature) = read_possibly_signed(path, target_mirror.reader)
        target = stream.Stream(load_content(content))
        if target.iqn != src_stream.iqn:
            raise TypeError("source content iqn (%s) != "
                            "mirrored content iqn (%s) at %s" %
                            (src_stream.iqn, target.iqn, path))
    except IOError as e:
        if e.errno != errno.ENOENT:
            raise
        target = stream.Stream({'iqn': src_stream.iqn,
                                'format': src_stream.format})

    sync_stream(src_stream, src_mirror, target, target_mirror, **kwargs)
    target_mirror.insert_object_content(path, src_content)

    return target


def sync_stream(src, src_mirror, target, target_store, **kwargs):
    (to_add, to_remove) = resolve_work(src.item_groups, target.item_groups,
                                       **kwargs)
    for item_group in to_add:
        target_store.insert_group(item_group, src_mirror.reader)
        target.item_groups.append(item_group)

    for item_group in to_remove:
        target_store.remove_group(item_group)
        target.item_groups.remove(item_group)


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise
    return
# vi: ts=4 expandtab

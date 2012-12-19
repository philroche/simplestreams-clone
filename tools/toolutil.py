#!/usr/bin/python

import errno
from Cheetah.Template import Template
import json
import os
import os.path
import subprocess
import yaml

PGP_SIGNED_MESSAGE_HEADER = "-----BEGIN PGP SIGNED MESSAGE-----"
PGP_SIGNATURE_HEADER = "-----BEGIN PGP SIGNATURE-----"
PGP_SIGNATURE_FOOTER = "-----END PGP SIGNATURE-----"


REL2VER = {
    "hardy": {'version': "8.04", 'devname': "Hardy Heron"},
    "lucid": {'version': "10.04", 'devname': "Lucid Lynx"},
    "oneiric": {'version': "11.10", 'devname': "Oneiric Ocelot"},
    "precise": {'version': "12.04", 'devname': "Precise Pangolin"},
    "quantal": {'version': "12.10", 'devname': "Quantal Quetzal"},
    "raring": {'version': "13.04", 'devname': "Raring Ringtail"},
}

def render_string(content, params):
    if not params:
        params = {}
    return Template(content, searchList=[params]).respond()


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise
    return


def read_possibly_signed(path):
    content = ""
    with open(path, "r") as cfp:
        content = cfp.read()

    if content.startswith(PGP_SIGNED_MESSAGE_HEADER):
        # http://rfc-ref.org/RFC-TEXTS/2440/chapter7.html
        subprocess.check_output(["gpg", "--batch", "--verify", path],
                                stderr=subprocess.STDOUT)
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


def signfile(path):
    tmpfile = "%s.tmp" % path
    os.rename(path, tmpfile)
    subprocess.check_output(["gpg", "--batch", "--output", path,
                             "--clearsign", tmpfile])
    os.unlink(tmpfile)


def dumps(content, fmt="yaml"):
    if fmt == "yaml":
        return yaml.safe_dump(content)
    else:
        return json.dumps(content)


def load_content(path):
    (content, signature) = read_possibly_signed(path)
    if path.endswith(".yaml"):
        return yaml.safe_load(content)
    else:
        return json.loads(content)


def process(cur, data, level, layout, callback, passthrough):
    for item in cur:
        if isinstance(item, dict):
            data[layout[level]['name']] = item.copy()
        else:
            data[layout[level]['name']] = {'name': item}

        curdatum = data[layout[level]['name']]

        if callable(layout[level].get('populate', None)):
            layout[level]['populate'](curdatum)

        if (level + 1) == len(layout):
            path = '/'.join([data[n['name']]['name'] for n in layout])
            callback(cur[item], data, path, passthrough)
        else:
            process(cur[item], data, level + 1, layout, callback,
                    passthrough)


def process_collections(stream_files, path_prefix, callback):
    collections = {}
    for url in stream_files:
        stream = load_content("%s/%s" % (path_prefix, url))
        ctok = ""
        for ptok in [""] + url.split("/")[:-1]:
            ctok += "%s/" % ptok
            if ctok not in collections:
                collections[ctok] = {'streams': []}
                collections[ctok]['tags'] = stream['tags'].copy()
            else:
                clear = []
                for key, val in collections[ctok]['tags'].iteritems():
                    if key not in stream['tags'] or stream['tags'][key] != val:
                        clear.append(key)
                for key in clear:
                    del collections[ctok]['tags'][key]

            collections[ctok]['streams'].append(
                {'tags': stream['tags'].copy(), 'url': url[len(ctok) - 1:]})

    for coll in collections:
        for stream in collections[coll]['streams']:
            for coll_tag in collections[coll]['tags']:
                if coll_tag in stream['tags']:
                    del stream['tags'][coll_tag]

        callback(path=coll, path_prefix=path_prefix,
                 collection=collections[coll])


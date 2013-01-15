#!/usr/bin/python

import errno
from Cheetah.Template import Template
import json
import os
import os.path
from simplestreams import read_possibly_signed
import subprocess
import yaml


REL2VER = {
    "hardy": {'version': "8.04", 'devname': "Hardy Heron"},
    "lucid": {'version': "10.04", 'devname': "Lucid Lynx"},
    "oneiric": {'version': "11.10", 'devname': "Oneiric Ocelot"},
    "precise": {'version': "12.04", 'devname': "Precise Pangolin"},
    "quantal": {'version': "12.10", 'devname': "Quantal Quetzal"},
    "raring": {'version': "13.04", 'devname': "Raring Ringtail"},
}

SKIP_COPY_UP = ( 'format' )

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

            addstream = {}
            addstream['tags'] = stream['tags'].copy()
            for topitem in stream:
                val = stream[topitem]
                if isinstance(val, str) and topitem not in SKIP_COPY_UP:
                    addstream[topitem] = val

            addstream['path'] = url
                    
            collections[ctok]['streams'].append(addstream)

    for coll in collections:
        for stream in collections[coll]['streams']:
            for coll_tag in collections[coll]['tags']:
                if coll_tag in stream['tags']:
                    del stream['tags'][coll_tag]

        callback(path=coll, path_prefix=path_prefix,
                 collection=collections[coll])

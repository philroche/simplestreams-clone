#!/usr/bin/python

import errno
from Cheetah.Template import Template
import json
import os
import os.path
from simplestreams.util import read_possibly_signed
import subprocess
import urllib2
import urlparse
import yaml


REL2VER = {
    "hardy": {'version': "8.04", 'devname': "Hardy Heron"},
    "lucid": {'version': "10.04", 'devname': "Lucid Lynx"},
    "oneiric": {'version': "11.10", 'devname': "Oneiric Ocelot"},
    "precise": {'version': "12.04", 'devname': "Precise Pangolin"},
    "quantal": {'version': "12.10", 'devname': "Quantal Quetzal"},
    "raring": {'version': "13.04", 'devname': "Raring Ringtail"},
}

SKIP_COPY_UP = ('format')


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


def signfile(path, output=None):
    if output is None:
        output = path + ".gpg"

    if os.path.exists(output):
        os.unlink(output)

    subprocess.check_output(["gpg", "--batch", "--output", output,
                             "--armor", "--sign", path])


def signfile_inline(path, output=None):
    infile = path
    tmpfile = None
    if output is None:
        # sign "in place" by using a temp file.
        tmpfile = "%s.tmp" % path
        os.rename(path, tmpfile)
        output = path
        infile = tmpfile
    elif os.path.exists(output):
        os.unlink(output)

    subprocess.check_output(["gpg", "--batch", "--output", output,
                             "--clearsign", infile])
    if tmpfile:
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


def tokenize_url(url):
    #given a url, find where the MIRROR.info file lives and return tokenized

    url_in = url

    while urlparse.urlparse(url).path:
        url = os.path.dirname(url)
        try:
            urllib2.urlopen("%s/%s" % (url, "MIRROR.info")).read()
            return (url + "/", url_in[len(url) + 1:])
        except urllib2.HTTPError as httperr:
            if httperr.code != 404:
                raise
        except urllib2.URLError as uerr:
            if ((isinstance(uerr.reason, OSError) and
                 uerr.reason.errno == errno.ENOENT)):
                pass
            else:
                raise

    raise TypeError("Unable to find MIRROR.info above %s" % url_in)


def signjs_file(fname, status_cb=None):
    content = ""
    with open(fname) as fp:
        content = fp.read()
    data = json.loads(content)
    fmt = data.get("format")
    sjs = fname[0:-len(".js")] + ".sjs"

    if status_cb is None:
        def null_cb(fname, fmt):
            pass
        status_cb = null_cb

    if fmt == "stream-collection:1.0":
        status_cb(fname, fmt)
        signfile(fname)
        for stream in data.get('streams'):
            path = stream.get('path')
            if path.endswith(".js"):
                stream['path'] = path[0:-len(".js")] + ".sjs"
        with open(sjs, "w") as fp:
            fp.write(json.dumps(data, indent=1))
        signfile_inline(sjs)
    elif fmt == "stream:1.0":
        status_cb(fname, fmt)
        signfile(fname)
        signfile_inline(fname, sjs)
    elif fmt is None:
        status_cb(fname, fmt)
        return
    else:
        status_cb(fname, fmt)
        return

# vi: ts=4 expandtab syntax=python

#!/usr/bin/python

import json
import os
import os.path

from simplestreams import util

REL2VER = {
    "hardy": {'version': "8.04", 'devname': "Hardy Heron"},
    "lucid": {'version': "10.04", 'devname': "Lucid Lynx"},
    "oneiric": {'version': "11.10", 'devname': "Oneiric Ocelot"},
    "precise": {'version': "12.04", 'devname': "Precise Pangolin"},
    "quantal": {'version': "12.10", 'devname': "Quantal Quetzal"},
    "raring": {'version': "13.04", 'devname': "Raring Ringtail"},
    "saucy": {'version': "13.10", 'devname': "Saucy Salamander"},
}

RELEASES = [k for k in REL2VER if k != "hardy"]
BUILDS = ("server")

NUM_DAILIES = 4


def is_expected(repl, fields):
    rel = fields[0]
    serial = fields[3]
    if repl == "-root.tar.gz":
        if rel in ("lucid", "oneiric"):
            # lucid, oneiric do not have -root.tar.gz
            return False
        if rel == "precise" and cmp(serial, "20120202") <= 0:
            # precise got -root.tar.gz after alpha2
            return False

    if repl == "-disk1.img":
        if rel == "lucid":
            return False
        if rel == "oneiric" and cmp(serial, "20110802.2") <= 0:
            # oneiric got -disk1.img after alpha3
            return False

    #if some data in /query is not truely available, fill up this array
    #to skip it. ex: export BROKEN="precise/20121212.1 quantal/20130128.1"
    broken = os.environ.get("BROKEN", "").split(" ")
    if "%s/%s" % (rel, serial) in broken:
        print("Known broken: %s/%s" % (rel, serial))
        return False

    return True


def load_query_download(path, builds=None, rels=None):
    if builds is None:
        builds = BUILDS
    if rels is None:
        rels = RELEASES

    streams = [f[0:-len(".latest.txt")]
               for f in os.listdir(path) if f.endswith("latest.txt")]

    results = []
    for stream in streams:
        dl_files = []

        latest_f = "%s/%s.latest.txt" % (path, stream)

        # get the builds and releases
        with open(latest_f) as fp:
            for line in fp.readlines():
                (rel, build, _stream, _serial) = line.split("\t")

                if ((len(builds) and build not in builds) or
                        (len(rels) and rel not in rels)):
                    continue

                dl_files.append("%s/%s/%s/%s-dl.txt" %
                                (path, rel, build, stream))

        field_path = 5
        field_name = 6
        # stream/build/release/arch
        for dl_file in dl_files:
            olines = open(dl_file).readlines()

            # download files in /query only contain '.tar.gz' (uec tarball)
            # file.  So we have to make up other entries.
            lines = []
            for oline in olines:
                for repl in (".tar.gz", "-root.tar.gz", "-disk1.img"):
                    fields = oline.rstrip().split("\t")
                    if not is_expected(repl, fields):
                        continue

                    new_path = fields[field_path].replace(".tar.gz", repl)

                    fields[field_path] = new_path
                    fields[field_name] += repl
                    lines.append("\t".join(fields) + "\n")

            for line in lines:
                line = line.rstrip("\n\r") + "\tBOGUS"

                results.append([stream] + line.split("\t", 8)[0:7])

    return results


def load_query_ec2(path, builds=None, rels=None, max_dailies=NUM_DAILIES):
    if builds is None:
        builds = BUILDS
    if rels is None:
        rels = RELEASES

    streams = [f[0:-len(".latest.txt")]
               for f in os.listdir(path) if f.endswith("latest.txt")]
    results = []

    for stream in streams:
        id_files = []

        latest_f = "%s/%s.latest.txt" % (path, stream)

        # get the builds and releases
        with open(latest_f) as fp:
            for line in fp.readlines():
                (rel, build, _stream, _serial) = line.split("\t")

                if ((len(builds) and build not in builds) or
                        (len(rels) and rel not in rels)):
                    continue

                id_files.append("%s/%s/%s/%s.txt" %
                                (path, rel, build, stream))

        for id_file in id_files:
            lines = reversed(open(id_file).readlines())
            serials_seen = 0
            last_serial = None
            for line in lines:
                line = line.rstrip("\n\r") + "\tBOGUS"
                ret = [stream]
                ret.extend(line.split("\t", 11)[0:11])

                if stream == "daily":
                    serial = ret[4]
                    if serial != last_serial:
                        serials_seen += 1
                    last_serial = serial
                    if serials_seen > max_dailies:
                        break

                results.append(ret)

    return results


def signjson_file(fname, status_cb=None):
    # input fname should be .json
    # creates .json.gpg and .sjson
    content = ""
    with open(fname) as fp:
        content = fp.read()
    (changed, scontent) = util.make_signed_content_paths(content)

    if status_cb:
        status_cb(fname)

    util.sign_file(fname, inline=False)
    if changed:
        util.sign_content(scontent, util.signed_fname(fname, inline=True),
                          inline=True)
    else:
        util.sign_file(fname, inline=True)

    return


# vi: ts=4 expandtab syntax=python

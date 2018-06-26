#!/usr/bin/python3
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

import os
import os.path

from ubuntu_versions import REL2VER, codename_cmp

BLACKLIST_RELS = ('hardy', 'intrepid', 'jaunty', 'karmic', 'maverick', 'natty')
RELEASES = [k for k in REL2VER if k not in BLACKLIST_RELS]
BUILDS = ("server")

NUM_DAILIES = 4


def is_expected(suffix, fields):
    """return boolean indicating if 'suffix' is expected for data in fields

       suffix is the part of the name that varies for a cloud image file
          given files like:
             ubuntu-15.10-server-cloudimg-i386.tar.gz
             wily-server-cloudimg-i386-root.tar.xz
          The common part is wily-server-cloudimg-i386.
          The suffix is the part after that.
            .tar.gz, -root.tar.gz, -disk1.img, -uefi1.img,
            .manifest, .ova, -root.tar.xz, -lxd.tar.xz ...

       fields are the fields from /query data. It is a tuple of
          rel, bname, label, serial, arch, path, pubname"""

    rel, bname, label, serial, arch, path, pubname = fields
    if suffix == "-root.tar.gz":
        # yakkety and forward do not have -root.tar.gz
        if codename_cmp(rel, ">=", "yakkety"):
            return False
        if codename_cmp(rel, "<=", "oneiric"):
            # lucid, oneiric do not have -root.tar.gz
            return False
        if rel == "precise" and serial <= "20120202":
            # precise got -root.tar.gz after alpha2
            return False

    if suffix == "-disk1.img":
        # disk1.img as a suffix was replaced by .img in yakkety
        if codename_cmp(rel, "<", "oneiric"):
            return False
        if codename_cmp(rel, ">=", "yakkety"):
            return False
        if rel == "oneiric" and serial <= "20110802.2":
            # oneiric got -disk1.img after alpha3
            return False

    if suffix == ".img":
        # .img files replaced -disk1.img in yakkety
        if codename_cmp(rel, "<", "yakkety") or serial < "20160512":
            return False

    if suffix == "-uefi1.img":
        if arch not in ["amd64", "arm64"]:
            return False
        # uefi images were released with trusty and removed in yakkety
        if codename_cmp(rel, "<", "trusty"):
            return False
        if codename_cmp(rel, ">=", "yakkety"):
            return False

    if arch == "ppc64el":
        if codename_cmp(rel, "<", "trusty") or serial <= "20140326":
            return False

    if suffix == ".ova":
        # OVA images become available after 20150407.4 (vivid beta-3)
        # and only for trusty and later x86
        if codename_cmp(rel, "<", "trusty") or serial < "20150407.4":
            return False
        # OVAs weren't produced properly for early first yakkety images
        if codename_cmp(rel, "=", "yakkety") and serial < "20160516.1":
            return False
        # For Bionic, and any release after Bionic, OVAs are not produced for
        # i386 after serial 20180213
        if (arch == 'i386' and codename_cmp(rel, ">=", "bionic") and
                serial > "20180213"):
            return False
        if arch not in ('i386', 'amd64'):
            return False

    if suffix == "-root.manifest":
        if codename_cmp(rel, '>=', 'cosmic'):
            # -root.manifest was introduced to cosmic in 20180612
            if serial >= '20180612':
                return True
        return False

    if suffix == "-root.tar.xz":
        if codename_cmp(rel, '>=', 'cosmic'):
            # -root.tar.xz was reintroduced to cosmic in 20180612
            if serial >= '20180612':
                return True

    if suffix == "-root.tar.xz" or suffix == "-lxd.tar.xz":
        # -root.tar.xz and -lxd.tar.xz become available after 20150714.3
        if serial < "20150714.4":
            return False
        if codename_cmp(rel, "<", "precise"):
            return False
        # -root.tar.xz is replaced by squashfs for yakkety
        if codename_cmp(rel, ">=", "yakkety") and suffix == '-root.tar.xz':
            return False

    if suffix == '.squashfs' or suffix == '.squashfs.manifest':
        # squashfs became available in the xenial cycle
        if codename_cmp(rel, "<", "xenial"):
            return False
        if rel == "xenial" and serial <= "20160420.3":
            return False

    # if some data in /query is not truely available, fill up this array
    # to skip it. ex: export BROKEN="precise/20121212.1 quantal/20130128.1"
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

    suffixes = (".tar.gz", "-root.tar.gz", "-disk1.img", "-uefi1.img",
                ".manifest", ".ova", "-root.tar.xz", "-root.manifest",
                "-lxd.tar.xz", ".squashfs", ".squashfs.manifest", ".img",)
    streams = [f[0:-len(".latest.txt")]
               for f in os.listdir(path) if f.endswith("latest.txt")]

    # releases prior to xenial published /query data referencing
    # the .tar.gz file.  xenial does not produce that at all,
    # so /query references another file.
    expected_qsuff = (".tar.gz", "-lxd.tar.xz", "-root.tar.xz")

    results = []
    for stream in streams:
        dl_files = []

        latest_f = "%s/%s.latest.txt" % (path, stream)

        # get the builds and releases
        with open(latest_f, "r") as fp:
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
            olines = open(dl_file, "r").readlines()

            # download files in /query only contain '.tar.gz' (uec tarball)
            # file.  So we have to make up other entries.
            lines = []
            for oline in olines:
                ofields = oline.rstrip().split("\t")
                fpath = ofields[field_path]
                qsuff = None
                for candidate in expected_qsuff:
                    if fpath.endswith(candidate):
                        qsuff = candidate
                if qsuff is None:
                    raise ValueError("%s had unexpected suffix in %s" %
                                     (dl_file, fpath))

                for repl in suffixes:
                    # copy for editing here.
                    fields = list(ofields)
                    if not is_expected(repl, fields):
                        continue

                    new_path = fields[field_path].replace(qsuff, repl)

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
        with open(latest_f, "r") as fp:
            for line in fp.readlines():
                (rel, build, _stream, _serial) = line.split("\t")

                if ((len(builds) and build not in builds) or
                        (len(rels) and rel not in rels)):
                    continue

                id_files.append("%s/%s/%s/%s.txt" %
                                (path, rel, build, stream))

        for id_file in id_files:
            lines = reversed(open(id_file, "r").readlines())
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


# vi: ts=4 expandtab syntax=python

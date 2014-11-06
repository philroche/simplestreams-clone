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

# this is only used if no distro_info available
HARDCODED_REL2VER = {
    "hardy": {'version': "8.04", 'devname': "Hardy Heron"},
    "lucid": {'version': "10.04", 'devname': "Lucid Lynx"},
    "oneiric": {'version': "11.10", 'devname': "Oneiric Ocelot"},
    "precise": {'version': "12.04", 'devname': "Precise Pangolin"},
    "quantal": {'version': "12.10", 'devname': "Quantal Quetzal"},
    "raring": {'version': "13.04", 'devname': "Raring Ringtail"},
    "saucy": {'version': "13.10", 'devname': "Saucy Salamander"},
    "trusty": {'version': "14.04", 'devname': "Trusty Tahr"},
    "utopic": {'version': "14.10", 'devname': "Utopic Unicorn"},
    "vivid": {'version': "15.04", 'devname': "Vivid Vervet"},
}


def get_ubuntu_info(date=None):
    # this returns a sorted list of dicts
    # each dict has information about an ubuntu release.
    # Notably absent is any date information (release or eol)
    # its harder than you'd like to get at data via the distro_info library
    #
    # The resultant dicts looks like this:
    # {'codename': 'saucy', 'devel': True,
    #  'full_codename': 'Saucy Salamander',
    #  'fullname': 'Ubuntu 13.10 "Saucy Salamander"',
    #  'lts': False, 'supported': True, 'version': '13.10'}

    udi = distro_info.UbuntuDistroInfo()
    # 'all' is a attribute, not a function. so we can't ask for it formated.
    # s2all and us2all are lists, the value of each is the index
    # where that release should fall in 'all'.
    allcn = udi.all
    s2all = [allcn.index(c) for c in
             udi.supported(result="codename", date=date)]
    us2all = [allcn.index(c) for c in
              udi.unsupported(result="codename", date=date)]

    def getall(result, date):
        ret = [None for f in range(0, len(allcn))]
        for i, r in enumerate(udi.supported(result=result, date=date)):
            ret[s2all[i]] = r
        for i, r in enumerate(udi.unsupported(result=result, date=date)):
            ret[us2all[i]] = r
        return [r for r in ret if r is not None]

    codenames = getall(result="codename", date=date)
    fullnames = getall(result="fullname", date=date)
    lts = [bool('LTS' in f) for f in fullnames]
    versions = [x.replace(" LTS", "") for x in
                getall(result="release", date=date)]
    full_codenames = [x.split('"')[1] for x in fullnames]
    supported = udi.supported(date=date)
    devel = udi.devel(date=date)
    ret = []
    for i, codename in enumerate(codenames):
        ret.append({'lts': lts[i], 'version': versions[i],
                    'supported': codename in supported,
                    'fullname': fullnames[i], 'codename': codename,
                    'devname': full_codenames[i],
                    'devel': bool(codename == devel)})

    return ret


try:
    import distro_info
    info = get_ubuntu_info()
    REL2VER = {}
    for r in info:
        if r['codename'] < "hardy":
            continue
        REL2VER[r['codename']] = {x: r[x] for x in ("version", "devname")}

except ImportError:
    REL2VER = HARDCODED_REL2VER

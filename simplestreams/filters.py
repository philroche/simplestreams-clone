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

from simplestreams import util

import re


class ItemFilter(object):
    def __init__(self, content, noneval=""):
        rparsefmt = r"([\w|\-]+)[ ]*([!]{0,1}[=~])[ ]*(.*)[ ]*$"
        parsed = re.match(rparsefmt, content)

        if not parsed:
            raise ValueError("Unable to parse expression %s" % content)

        (key, op, val) = parsed.groups()

        if op in ("!=", "="):
            self._matches = val.__eq__
        elif op in ("!~", "~"):
            self._matches = re.compile(val).search
        else:
            raise ValueError("Bad parsing of %s" % content)

        self.negator = (op[0] != "!")
        self.op = op
        self.key = key
        self.value = val
        self.content = content
        self.noneval = noneval

    def __str__(self):
        return "%s %s %s [none=%s]" % (self.key, self.op,
                                       self.value, self.noneval)

    def __repr__(self):
        return self.__str__()

    def matches(self, item):
        val = str(item.get(self.key, self.noneval))
        return (self.negator == bool(self._matches(val)))


def get_filters(filters, noneval=""):
    flist = []
    for f in filters:
        flist.append(ItemFilter(f, noneval=noneval))
    return flist


def filter_item(filters, data, src, pedigree):
    "Apply filter list to a products entity.  Flatten before doing so."
    return filter_dict(filters, util.products_exdata(src, pedigree))


def filter_dict(filters, data):
    "Apply filter list to dict. Does not flatten."
    for f in filters:
        if not f.matches(data):
            return False
    return True

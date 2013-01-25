# vi: ts=4 expandtab
import simplestreams
from items import ItemGroupList as igl

RESTRICTED_TYPES = {"format": str, "streams": list}
REQUIRED = ("format")


class CollectionStreamEntry(dict):
    def __init__(self, data, parent=None):
        self.parent = parent
        super(self.__class__, self).__init__(data.copy())

    @property
    def alltags(self):
        return simplestreams.alltags(self, self.parent)

    @property
    def tags(self):
        return {k: self[k] for k in self if
                k not in ('name', 'path', 'md5sum', 'sha512', 'sha256')}


class CollectionStreamList(simplestreams.RestrictedSimpleParentedList):
    restriction = CollectionStreamEntry


class Collection(dict):
    def __init__(self, data):
        validate_dict(data)

        mdata = data.copy()
        if 'streams' not in mdata:
            mdata['streams'] = []

        if 'tags' not in mdata:
            mdata['tags'] = {}

        mdata['streams'] = CollectionStreamList(mdata['streams'], parent=self)

        super(Collection, self).__init__(mdata)

    def _getattr(self, name):
        return self.get(name)

    def _set(self, name, value):
        validate(name, value)
        self[name] = value

    @property
    def iqn(self):
        return self.get('iqn')

    @property
    def description(self):
        return self._getattr('description')

    @description.setter
    def description(self, value):
        self._set('description', value)

    @property
    def streams(self):
        return self.get('streams')

    @streams.setter
    def streams(self, value):
        self._set('streams', value)

    @property
    def format(self):
        return self.get('format')

    @format.setter
    def format(self, value):
        self._set('format', value)

    @property
    def tags(self):
        return self.get('tags')

    def as_dict(self):
        return simplestreams.as_dict(self)

    def flattened(self):
        ret = {k: v for k, v in self.iteritems() if isinstance(v, str)}
        ret.update(self.tags())
        return ret


def validate(name, value):
    rtype = RESTRICTED_TYPES[name]
    if not isinstance(value, rtype):
        raise TypeError("input data %s not a %s" % (name, rtype))


def validate_dict(data):
    if not isinstance(data, dict):
        raise TypeError("data input not a dict")
    for name in RESTRICTED_TYPES:
        if name in data:
            validate(name, data.get(name))
        elif name in REQUIRED:
            raise TypeError("input data did not contain %s" % name)

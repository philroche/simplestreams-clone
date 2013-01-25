from items import ItemGroupList as igl
from simplestreams import as_dict

RESTRICTED_TYPES = {"iqn": str, "format": str, "item_groups": list}
REQUIRED = ("iqn", "format")


class Stream(dict):
    def __init__(self, data):
        validate_dict(data)

        mdata = data.copy()
        if 'item_groups' not in mdata:
            mdata['item_groups'] = []

        if 'tags' not in mdata:
            mdata['tags'] = {}

        mdata['item_groups'] = igl(mdata['item_groups'], parent=self)

        super(Stream, self).__init__(mdata)

    def _getattr(self, name):
        return self.get(name)

    def _set(self, name, value):
        validate(name, value)
        self[name] = value

    @property
    def iqn(self):
        return self.get('iqn')

    @iqn.setter
    def iqn(self, value):
        self._set('iqn', value)

    @property
    def description(self):
        return self._getattr('description')

    @description.setter
    def description(self, value):
        self._set('description', value)

    @property
    def item_groups(self):
        return self.get('item_groups')

    @item_groups.setter
    def item_groups(self, value):
        self._set('item_groups', value)

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
        return as_dict(self)

    def flattened(self):
        ret = { k: v for k, v in self.iteritems() if isinstance(v, str) }
        ret.update(self.tags)
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

# vi: ts=4 expandtab

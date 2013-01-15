import simplestreams

SUM_NAMES = ("md5sum", "sha256sum", "sha512sum")


class ItemGroup(dict):
    """ItemGroup is a group of Items."""
    parent = None

    def __init__(self, data, parent=None):
        if 'serial' not in data:
            raise TypeError("missing required field serial")

        mdata = data.copy()
        mdata['items'] = ItemList(mdata.get('items', []), parent=self)

        self.parent = parent

        super(ItemGroup, self).__init__(mdata)

    def __cmp__(self, other):
        return cmp(self['serial'], other['serial'])

    def __eq__(self, other):
        return (self['serial'] == other['serial'])

    def __hash__(self):
        return self['serial']

    @property
    def tags(self):
        return {k: self[k] for k in self if k not in ('serial', 'items')}

    @property
    def alltags(self):
        return simplestreams.alltags(self, self.parent)

    @property
    def items(self):
        return self['items']

#class ItemList(list):
#    """ItemList is a list of Item types."""
#    parent = None
#
#    def __init__(self, data, parent=None):
#        self.parent = parent
#        for i in range(0, len(data)):
#            if not isinstance(data[i], Item):
#                data[i] = Item(data[i], parent=self)
#        super(self.__class__, self).__init__(data)
#
#    @property
#    def alltags(self):
#        return parent_tags(self.parent)


class Item(dict):
    """Item is unit/file.  One of a ItemList (like items). name is unique"""

    def __init__(self, data, parent=None):
        self.parent = parent
        if not 'name' in data:
            raise TypeError("required field 'name' missing")

        super(self.__class__, self).__init__(data.copy())

    def __hash__(self):
        return self['name']

    def __cmp__(self, other):
        return cmp(self['name'], other['name'])

    @property
    def alltags(self):
        return simplestreams.alltags(self, self.parent)

    @property
    def tags(self):
        return {k: self[k] for k in self if
                k not in ('name', 'path', 'md5sum', 'sha512', 'sha256')}


class ItemList(simplestreams.RestrictedSimpleParentedList):
    restriction = Item


class ItemGroupList(simplestreams.RestrictedSimpleParentedList):
    restriction = ItemGroup


# vi: ts=4 expandtab

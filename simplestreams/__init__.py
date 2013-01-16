CHECKSUMS = ("md5", "sha512")


class RestrictedSimpleParentedList(list):
    """A simple list with parent attr, and restriction on types inserted"""
    parent = None
    restriction = None

    def __init__(self, data, parent=None):
        self.parent = parent

        mdata = []
        if self.restriction:
            for i in range(0, len(data)):
                mdata.append(self.restriction(data[i], parent=self))

        super(RestrictedSimpleParentedList, self).__init__(mdata)

    @property
    def alltags(self):
        return parent_tags(self.parent)

    def append(self, item):
        to_add = item
        if self.restriction:
            to_add = self.restriction(item, parent=self)
        super(RestrictedSimpleParentedList, self).append(to_add)


def parent_tags(parent):
    if hasattr(parent, "alltags"):
        return parent.alltags
    if hasattr(parent, "tags"):
        return parent.tags.copy()
    return {}


def alltags(cur, parent):
    tags = {}
    tags.update(cur.tags)
    tags.update(parent_tags(parent))
    return tags


# vi: ts=4 expandtab

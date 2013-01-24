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

def get_iqn(cur):
    while hasattr(cur, 'parent'):
        if hasattr(cur.parent, 'iqn'):
            return cur.parent.iqn
        cur = cur.parent
    return None


def as_dict(obj, classkey=None):
    if isinstance(obj, dict):
        data = {}
        for k in obj.keys():
            data[k] = as_dict(obj[k], classkey)
        return data
    elif hasattr(obj, "__iter__"):
        return [as_dict(v, classkey) for v in obj]
    elif hasattr(obj, "__dict__"):
        data = dict([(key, as_dict(value, classkey)) 
            for key, value in obj.__dict__.iteritems() 
            if not callable(value) and not key.startswith('_')])
        if classkey is not None and hasattr(obj, "__class__"):
            data[classkey] = obj.__class__.__name__
        return data
    else:
        return obj


# vi: ts=4 expandtab

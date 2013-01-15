PGP_SIGNED_MESSAGE_HEADER = "-----BEGIN PGP SIGNED MESSAGE-----"
PGP_SIGNATURE_HEADER = "-----BEGIN PGP SIGNATURE-----"
PGP_SIGNATURE_FOOTER = "-----END PGP SIGNATURE-----"


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


def resolve_work(src, target, max=None, keep=None, sort_reverse=True):
    add = []
    remove = []
    reverse = sort_reverse

    if keep is not None and max is not None and max > keep:
        raise TypeError("max: %s larger than keep: %s" % (max, keep))

    for item in sorted(src, reverse=reverse):
        if item not in target:
            add.append(item)

    for item in sorted(target, reverse=reverse):
        if item not in src:
            remove.append(item)

    if keep is not None and len(remove):
        after_add = len(target) + len(add)
        while len(remove) and keep > (after_add - len(remove)):
            remove.pop(0)

    final_count = (len(add) + len(target) - len(remove))
    if max is not None and final_count >= max:
        for i in range(0, final_count - max):
            add.pop()

    final_count = (len(add) + len(target) - len(remove))
    if max is not None and final_count > max:
        after_rem = sorted(list(set(target) - set(remove)), reverse=reverse)
        remove.append(after_rem[:-(final_count - max)])

    return(add, remove)


def read_possibly_signed(path):
    content = ""
    with open(path, "r") as cfp:
        content = cfp.read()

    if content.startswith(PGP_SIGNED_MESSAGE_HEADER):
        # http://rfc-ref.org/RFC-TEXTS/2440/chapter7.html
        subprocess.check_output(["gpg", "--batch", "--verify", path],
                                stderr=subprocess.STDOUT)
        ret = {'body': '', 'signature': '', 'garbage': ''}
        lines = content.splitlines()
        i = 0
        for i in range(0, len(lines)):
            if lines[i] == PGP_SIGNED_MESSAGE_HEADER:
                mode = "header"
                continue
            elif mode == "header":
                if lines[i] != "":
                    mode = "body"
                continue
            elif lines[i] == PGP_SIGNATURE_HEADER:
                mode = "signature"
                continue
            elif lines[i] == PGP_SIGNATURE_FOOTER:
                mode = "garbage"
                continue

            # dash-escaped content in body
            if lines[i].startswith("- ") and mode == "body":
                ret[mode] += lines[i][2:] + "\n"
            else:
                ret[mode] += lines[i] + "\n"

        return(ret['body'], ret['signature'])
    else:
        return(content, None)



# vi: ts=4 expandtab

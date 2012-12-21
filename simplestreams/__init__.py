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

# vi: ts=4 expandtab

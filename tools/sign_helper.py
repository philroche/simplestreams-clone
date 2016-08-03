import os

from simplestreams import util


def signjson_file(fname, status_cb=None, force=True):
    # input fname should be .json
    # creates .json.gpg and .sjson
    content = ""
    with open(fname, "r") as fp:
        content = fp.read()
    if not force:
        octime = os.path.getctime(fname)
        output = [util.signed_fname(fname, inline=b) for b in (True, False)]
        update = [f for f in output
                  if not (os.path.isfile(f) and octime < os.path.getctime(f))]
        if len(update) == 0:
            return

    (changed, scontent) = util.make_signed_content_paths(content)

    if status_cb:
        status_cb(fname)

    util.sign_file(fname, inline=False)
    if changed:
        util.sign_content(scontent, util.signed_fname(fname, inline=True),
                          inline=True)
    else:
        util.sign_file(fname, inline=True)

    return


# vi: ts=4 expandtab syntax=python

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

import simplestreams.mirrors as mirrors
import simplestreams.util as util

import os
import errno
import signal
import subprocess
import tempfile

REQUIRED_FIELDS = ("load_products",)
HOOK_NAMES = (
    "filter_index_entry",
    "filter_item",
    "filter_product",
    "filter_version",
    "insert_index",
    "insert_index_entry",
    "insert_item",
    "insert_product",
    "insert_products",
    "insert_version",
    "load_products",
    "remove_item",
    "remove_product",
    "remove_version",
)

DEFAULT_HOOK_NAME = "hook"
ENV_HOOK_NAME = "HOOK"
ENV_FIELDS_NAME = "FIELDS"


class CommandHookMirror(mirrors.BasicMirrorWriter):
    """
    CommandHookMirror: invoke commands to implement a SimpleStreamMirror

    Available command hooks:
      load_products:
        invoked to list items in the products in a given content_id.
        See product_load_output_format.

      filter_index_entry, filter_item, filter_product, filter_version:
        invoked to determine if the named entity should be operated on
        exit 0 for "yes", 1 for "no".

      insert_index, insert_index_entry, insert_item, insert_product,
      insert_products, insert_version :
        invoked to insert the given entity.

      remove_product, remove_version, remove_item:
        invoked to remove the given entity


    Other Configuration:
      product_load_output_format: one of [serial_list, json]
        serial_list: The default output should be white space delimited
                     output of product_name and version.
        json: output should be a json formated dictionary formated like
              products:1.0 content.

    Environments / Variables:
      When a hook is invoked, data about the relevant entity is
      made available in the environment.

      In all cases:
        * a special 'FIELDS' key is available which is a space delimited
          list of keys
        * a special 'HOOK' field is available that specifies which
          hook is being called.

      For an item in a products:1.0 file that has a 'path' item, the item
      will be downloaded and a 'path_local' field inserted into the metadata
      which will contain the path to the local file.

      If the configuration setting 'item_skip_download' is set to True, then
      'path_url' will be set instead to a url where the item can be found.
    """
    def __init__(self, config):
        if isinstance(config, str):
            config = util.load_content(config)
        check_config(config)

        super(CommandHookMirror, self).__init__(config=config)

    def load_products(self, path=None, content_id=None):
        (_rc, output) = self.call_hook('load_products',
                                       data={'content_id': content_id},
                                       capture=True)
        fmt = self.config.get("product_load_output_format", "serial_list")

        loaded = load_product_output(output=output, content_id=content_id,
                                     fmt=fmt)
        return loaded

    def filter_index_entry(self, data, src, pedigree):
        mdata = util.stringitems(src)
        mdata['content_id'] = pedigree[0]
        mdata.update(util.stringitems(data))

        (ret, _output) = self.call_hook('filter_index_entry', data=mdata,
                                        rcs=[0, 1])
        return ret == 0

    def filter_product(self, data, src, target, pedigree):
        return self._call_filter('filter_product', src, pedigree)

    def filter_version(self, data, src, target, pedigree):
        return self._call_filter('filter_version', src, pedigree)

    def filter_item(self, data, src, target, pedigree):
        return self._call_filter('filter_item', src, pedigree)

    def _call_filter(self, name, src, pedigree):
        data = util.products_exdata(src, pedigree)
        (ret, _output) = self.call_hook(name, data=data, rcs=[0, 1])
        return ret == 0

    def insert_index(self, path, src, content):
        return self.call_hook('insert_index', data=src, content=content,
                              extra={'path': path})

    def insert_products(self, path, target, content):
        return self.call_hook('insert_products', data=target,
                              content=content, extra={'path': path})

    def insert_product(self, data, src, target, pedigree):
        return self.call_hook('insert_product',
                              data=util.products_exdata(src, pedigree))

    def insert_version(self, data, src, target, pedigree):
        return self.call_hook('insert_version',
                              data=util.products_exdata(src, pedigree))

    def insert_item(self, data, src, target, pedigree, contentsource):
        mdata = util.products_exdata(src, pedigree)

        tmp_path = None
        tmp_del = None
        extra = {}
        if 'path' in data:
            extra.update({'item_url': contentsource.url})
            if not self.config.get('item_skip_download', False):
                try:
                    (tmp_path, tmp_del) = util.get_local_copy(contentsource)
                    extra['path_local'] = tmp_path
                finally:
                    contentsource.close()

        try:
            ret = self.call_hook('insert_item', data=mdata, extra=extra)
        finally:
            if tmp_del and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        return ret

    def remove_product(self, data, src, target, pedigree):
        return self.call_hook('remove_product',
                              data=util.products_exdata(src, pedigree))

    def remove_version(self, data, src, target, pedigree):
        return self.call_hook('remove_version',
                              data=util.products_exdata(src, pedigree))

    def remove_item(self, data, src, target, pedigree):
        return self.call_hook('remove_item',
                              data=util.products_exdata(target, pedigree))

    def call_hook(self, hookname, data, capture=False, rcs=None, extra=None,
                  content=None):
        command = self.config.get(hookname, self.config.get(DEFAULT_HOOK_NAME))
        if not command:
            # return successful execution with no output
            return (0, '')

        if isinstance(command, str):
            command = ['sh', '-c', command]

        fdata = util.stringitems(data)

        content_file = None
        if content is not None:
            (tfd, content_file) = tempfile.mkstemp()
            tfile = os.fdopen(tfd, "w")
            tfile.write(content)
            tfile.close()
            fdata['content_file_path'] = content_file

        if extra:
            fdata.update(extra)
        fdata['HOOK'] = hookname

        try:
            return call_hook(command=command, data=fdata,
                             unset=self.config.get('unset_value', None),
                             capture=capture, rcs=rcs)
        finally:
            if content_file:
                os.unlink(content_file)


def call_hook(command, data, unset=None, capture=False, rcs=None):
    env = os.environ.copy()
    data = data.copy()

    data[ENV_FIELDS_NAME] = ' '.join([k for k in data if k != ENV_HOOK_NAME])

    mcommand = render(command, data, unset=unset)

    env.update(data)
    return run_command(mcommand, env=env, capture=capture, rcs=rcs)


def render(inputs, data, unset=None):
    fdata = data.copy()
    outputs = []
    for i in inputs:
        while True:
            try:
                outputs.append(i % fdata)
                break
            except KeyError as err:
                if unset is None:
                    raise
                for key in err.args:
                    fdata[key] = unset
    return outputs


def check_config(config):
    missing = []
    for f in REQUIRED_FIELDS:
        if f not in config and config.get(DEFAULT_HOOK_NAME) is None:
            missing.append(f)
    if missing:
        raise TypeError("Missing required config entries for %s" % missing)


def load_product_output(output, content_id, fmt="serial_list"):
    # parse command output and return

    if fmt == "serial_list":
        # "line" format just is a list of serials that are present
        working = {'content_id': content_id, 'products': {}}
        for line in output.splitlines():
            (product_id, version) = line.split(None, 1)
            if product_id not in working['products']:
                working['products'][product_id] = {'versions': {}}
            working['products'][product_id]['versions'][version] = {}
        return working

    elif fmt == "json":
        return util.load_content(output)

    return


def run_command(cmd, env=None, capture=False, rcs=None):
    if not rcs:
        rcs = [0]

    if not capture:
        stdout = None
    else:
        stdout = subprocess.PIPE

    sp = subprocess.Popen(cmd, env=env, stdout=stdout, shell=False)
    (out, _err) = sp.communicate()
    rc = sp.returncode

    if rc == 0x80 | signal.SIGPIPE:
        exc = IOError("Child Received SIGPIPE: %s" % str(cmd))
        exc.errno = errno.EPIPE
        raise exc

    if rc not in rcs:
        raise subprocess.CalledProcessError(rc, cmd)

    if out is None:
        out = ''
    elif isinstance(out, bytes):
        out = out.decode('utf-8')

    return (rc, out)

# vi: ts=4 expandtab syntax=python

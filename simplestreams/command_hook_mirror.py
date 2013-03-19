import simplestreams.mirrors as mirrors
import simplestreams.util as util

import os
import subprocess
import tempfile
import yaml

READ_SIZE = (1024 * 1024)

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

DEFAULT_HOOK_NAME = "command"
ENV_HOOK_NAME = "HOOK"
ENV_FIELDS_NAME = "FIELDS"


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
  product_load_output_format: one of [serial_list, yaml]
    serial_list: The default output should be white space delimited
                 output of product_name and version.
    yaml: output should be a yaml formated dictionary formated like
          products:1.0 content.  Note, json is a proper subset of
          yaml, so it is acceptable to output json content.

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


class CommandHookMirror(mirrors.BasicMirrorWriter):
    def __init__(self, config):
        if isinstance(config, str):
            config = yaml.safe_load(config)
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

    def filter_index_entry(self, content_id, content, tree, pedigree):
        data = util.stringitems(tree)
        data['content_id'] = content_id
        data.update(util.stringitems(content))

        (ret, _output) = self.call_hook('filter_index_entry', data=data,
                                        rcs=[0, 1])
        return ret == 0

    def filter_product(self, product_id, product, tree, pedigree):
        return self._call_filter('filter_product', tree, pedigree)

    def filter_version(self, version_id, version, tree, pedigree):
        return self._call_filter('filter_version', tree, pedigree)

    def filter_item(self, item_id, item, tree, pedigree):
        return self._call_filter('filter_item', tree, pedigree)

    def _call_filter(self, name, tree, pedigree):
        data = util.products_exdata(tree, pedigree)
        (ret, _output) = self.call_hook(name, data=data, rcs=[0, 1])
        return ret == 0

    def insert_index(self, path, index, content):
        return self.call_hook('insert_index', data=index, content=content,
                              extra={'path': path})

    def insert_index_entry(self, contentsource, content_id, content, tree,
                           pedigree):
        pass

    def insert_products(self, path, products, content):
        return self.call_hook('insert_products', data=products,
                              content=content, extra={'path': path})

    def insert_product(self, product_id, product, tree, pedigree):
        return self.call_hook('insert_product',
                              data=util.products_exdata(tree, pedigree))

    def insert_version(self, version_id, version, tree, pedigree):
        return self.call_hook('insert_version',
                              data=util.products_exdata(tree, pedigree))

    def insert_item(self, contentsource, item_id, item, tree, pedigree):
        data = util.products_exdata(tree, pedigree)

        tmp_path = None
        tmp_del = None
        extra = {}
        if 'path' in item:
            extra.update({'item_url': contentsource.url})
            if not self.config.get('item_skip_download', False):
                try:
                    (tmp_path, tmp_del) = get_local_copy(contentsource.read)
                    extra['path_local'] = tmp_path
                finally:
                    contentsource.close()

        try:
            ret = self.call_hook('insert_item', data=data, extra=extra)
        finally:
            if tmp_del and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        return ret

    def remove_product(self, product_id, product, tree, pedigree):
        return self.call_hook('remove_product',
                              data=util.products_exdata(tree, pedigree))

    def remove_version(self, version_id, version, tree, pedigree):
        return self.call_hook('remove_version',
                              data=util.products_exdata(tree, pedigree))

    def remove_item(self, item_id, item, tree, pedigree):
        return self.call_hook('remove_item',
                              data=util.products_exdata(tree, pedigree))

    def call_hook(self, hookname, data, capture=False, rcs=None, extra=None,
                  content=None):
        command = self.config.get(hookname, self.config.get(DEFAULT_HOOK_NAME))
        if not command:
            # return successful execution with no output
            return (0, '')

        if isinstance(command, str):
            command = ['sh', '-c', command]

        print "calling hook: %s" % hookname
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
            (product_id, version) = line.split(maxsplit=1)
            if product_id not in working['products']:
                working['products'][content_id] = {'versions': {}}
            working['products'][content_id]['versions'][version] = {}
        return working

    elif fmt == "yaml":
        return yaml.safe_load(output)

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

    if rc not in rcs:
        raise subprocess.CalledProcessError(rc, cmd)

    if out is None:
        out = ''
    return (rc, out)


def get_local_copy(read, read_size=READ_SIZE):
    (tfd, tpath) = tempfile.mkstemp()
    tfile = os.fdopen(tfd, "w")
    try:
        while True:
            buf = read(read_size)
            tfile.write(buf)
            if len(buf) != read_size:
                break
        return (tpath, True)

    except Exception as e:
        os.unlink(tpath)
        raise e

# vi: ts=4 expandtab syntax=python

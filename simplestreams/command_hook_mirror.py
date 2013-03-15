import os
from simplestreams.objectstores import SimpleStreamMirrorWriter
from simplestreams.stream import Stream
from simplestreams import util
import subprocess
import tempfile
import yaml

READ_SIZE = (1024 * 1024)

REQUIRED_FIELDS = ("product_load",)
HOOK_NAMES = (
    "collection_store",
    "version_insert_post",
    "version_insert_pre",
    "version_remove_post",
    "version_remove_pre",
    "item_filter",
    "item_insert",
    "item_remove",
    "product_filter",
    "product_load",
    "product_store",
    )
DEFAULT_HOOK_NAME = "command"
ENV_HOOK_NAME = "HOOK"
ENV_FIELDS_NAME = "FIELDS"


"""
CommandHookMirror: invoke commands to implement a SimpleStreamMirror

Available command hooks:
  product_load:
    invoked to list items in the product. See product_load_output_format.
  product_store:
    invoked to store the product, after all add/remove have been done.

  collection_store:
    invoked to store a collection after all add/remove have been done.

  version_insert_pre
  version_insert_post
  version_remove_pre
  version_remove_post
    invoked with the version information before and after add/remove
    of a item in the version.

  product_filter:
    invoked to determine if a product should be operated on
    exit 0 for "yes", 1 for "no".

  item_filter
    invoked to determine if this item should be operated on
    exit 0 for "yes", 1 for "no"

  item_insert
    insert the item.

  item_remove
    remove the item.


Other Configuration:
  product_load_output_format: one of [serial_list, yaml]
    serial_list: The default output should be one serial per line
                 representing a version that is present
    yaml: output should be a dictionary that can be passed into
          loaded via yaml.safe_load and passed to Stream()

  unset_value: string, default is '_unset'
    This value is substituted for any invalid %() references
    when invoking a command.

Environments / Variables:
  When a hook is invoked, data about the relevant entity is
  made available in 2 ways:
   a.) through environment variables
   b.) through substitution of commands

  Each type of data has some fields guaranteed and others optional.

  In all cases:
    * a special 'FIELDS' key is available which is a space delimited
      list of keys
    * all 'tags' for the item (and parent items that apply) will be
      available.
    * a special 'HOOK' field is available that specifies which
      hook is being called.

  item:
    guaranteed: iqn, name, serial
    other: path_local
     * path_local: if the item has a 'path', then it is downloaded
                   and made available as a file pointed to by 'path_local'
  group:
    guaranteed: iqn, serial
"""


class CommandHookMirror(SimpleStreamMirrorWriter):
    def __init__(self, config):
        if isinstance(config, str):
            config = yaml.safe_load(config)
        check_config(config)
        self.config = config

    def load_product(self, path, prodname):
        (_rc, output) = self.call_hook('product_load',
                                       data={'product': prodname},
                                       capture=True)
        fmt = self.config.get("product_load_output_format", "serial_list")

        loaded = load_product_output(output=output, prodname=prodname, fmt=fmt)
        return loaded

    def store_product(self, path, product):
        self.call_hook('product_store', data=product,
                       extra={'path': path})

    def store_products(self, path, products, content):
        self.call_hook('products_store', data=products, content=content,
                       extra={'path': path})

    def insert_version(self, version, reader):
        self.call_hook('version_insert_pre', data=version)
        for item in version['items']:
            self.insert_item(item, reader)

        self.call_hook('version_insert_post', data=version)

    def remove_version(self, version):
        self.call_hook('version_remove_pre', data=version)
        for item in version['items']
            self.remove_item(item)

        self.call_hook('version_remove_post', data=version)

    def filter_product(self, product):
        return not self.product_is_filtered(product)

    def filter_version(self, version):
        return not self.version_is_filtered(version)

    def version_is_filtered(self, version):
        (ret, _output) = self.call_hook('version_filter', version, rcs=[0, 1])
        return ret == 1
        
    def item_is_filtered(self, item):
        (ret, _output) = self.call_hook('item_filter', item, rcs=[0, 1])
        return ret == 1

    def product_is_filtered(self, product):
        (ret, _output) = self.call_hook('product_filter', product, rcs=[0, 1])
        return ret == 1

    def insert_item(self, item, reader):
        if self.item_is_filtered(item):
            return

        tfile_path = None
        tfile_del = None

        extra = {}
        if item.path:
            with reader(item.path) as rfp:
                if not self.config.get('item_skip_download', False):
                    (tfile_path, tfile_del) = get_local_copy(rfp.read)
                    extra.update({'path_local': tfile_path})
                extra.update({'item_url': rfp.url})

        try:
            self.call_hook('item_insert', item, extra=extra)
        finally:
            if tfile_del and os.path.exists(tfile_path):
                os.unlink(tfile_path)

    def remove_item(self, item):
        if self.item_is_filtered(item):
            return
        self.call_hook('item_remove', item)

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


def load_product_output(output, prodname, fmt="serial_list"):
    # parse command output and return

    if fmt == "serial_list":
        # "line" format just is a list of serials that are present
        working = {'versions': {}}
        versions = working['versions']
        seen = []
        for line in output.splitlines():
            versions[line] = {}
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

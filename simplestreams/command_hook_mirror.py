import os
from simplestreams.objectstores import SimpleStreamMirrorWriter
from simplestreams.stream import Stream
import subprocess
import tempfile
import yaml

REQUIRED_FIELDS = ("stream_load",)
READ_SIZE = (1024 * 1024)

"""
CommandHookMirror: invoke commands to implement a SimpleStreamMirror

Available command hooks:
  stream_load:
    invoked to list items in the stream. See stream_load_output_format.
  stream_store:
    invoked to store the stream, after all add/remove have been done.

  collection_store:
    invoked to store a collection after all add/remove have been done.

  group_insert_pre
  group_insert_post
  group_remove_pre
  group_remove_post
    invoked with the group information before and after add/remove
    of a group.  Only groups with non-filtered items will be called.

  stream_filter:
    invoked to determine if a stream should be operated on
    exit 0 for "yes", 1 for "no".

  item_filter
    invoked to determine if this item should be operated on
    exit 0 for "yes", 1 for "no"

  item_insert
    insert the item.  there will be a 'local_path' exposed for
    a local path to the file.

  item_remove
    remove the item.


Other Configuration:
  stream_load_output_format: one of [serial_list, yaml]
    serial_list: The default output should be one serial per line
                 representing an item_groups serial that is present
    yaml: output should be a dictionary that can be passed into
          loaded via yaml.safe_load and passed to Stream()

  unset_value: string, default is '_unset'
    This value is substituted for any invalid %() references
    when invoking a command.
    
"""


class CommandHookMirror(SimpleStreamMirrorWriter):
    def __init__(self, config):
        if isinstance(config, str):
            config = yaml.safe_load(config)
        check_config(config)
        self.config = config

    def load_stream(self, path, reference=None):
        (_rc, output) = self.hook_stream('load', data=reference,
                                       capture=True)
        return load_stream_output(
            output=output,
            fmt=self.config.get("stream_load_output_format", "serial_list"),
            reference=reference)

    def store_stream(self, path, stream, content):
        self.hook_stream('store', data=stream,
                         extra={'content': content, 'path': path})

    def store_collection(self, path, collection, content):
        data = collection_data(collection, {'content': content, 'path': path})
        self.call_hook('collection_store', data)

    def insert_group(self, group, reader):
        items = [i for i in group.items if not self.item_is_filtered(i)]
        if not items:
            return

        self.hook_group('insert_pre', group)
        for item in items:
            self.insert_item(item, reader)

        self.hook_group('insert_post', group)

    def remove_group(self, group):
        items = [i for i in group.items if not self.item_is_filtered(i)]
        if not items:
            return

        self.hook_group('remove_pre', group)
        for item in items:
            self.remove_item(item)

        self.hook_group('remove_post', group)

    def item_is_filtered(self, item):
        (ret, _output) = self.hook_item('filter', item, rcs=[0, 1])
        return ret == 1

    def stream_is_filtered(self, stream):
        (ret, _output) = self.hook_stream('filter', stream, rcs=[0, 1])
        return ret == 1

    def insert_item(self, item, reader):
        tmp_item = item.copy()
        tfile_path = None
        tfile_del = None

        if item.path:
            (tfile_path, tfile_del) = get_local_copy(reader, item.path)
            tmp_item['local_path'] = tfile_path

        try:
            self.hook_item('insert', item)
        finally:
            if tfile_del and os.path.exists(tfile_path):
                os.unlink(tfile_path)

    def remove_item(self, item):
        self.hook_item('remove', item)

    def hook_group(self, action, data):
        return self.call_hook("group_%s" % action, group_data(data))

    def hook_stream(self, action, data, capture=False, rcs=None, extra=None):
        return self.call_hook("stream_%s" % action,
                              data=stream_data(data, extra=extra),
                              capture=capture, rcs=rcs)

    def hook_item(self, action, data, rcs=None):
        return self.call_hook("item_%s" % action, data=item_data(data),
                              rcs=rcs)

    def call_hook(self, hookname, data, capture=False, rcs=None):
        hook = self.config.get(hookname)
        if not hook:
            # return successful execution with no output
            return (0, '')

        if isinstance(hook, str):
            hook = ['sh', '-c', hook]
        
        margs = []
        full_data = data.copy()
        full_data['_all'] = ' '.join(data.keys())
        unset = self.config.get('unset_value', '_unset')

        margs = render(hook, data, unset=unset)

        return run_command(args=margs, capture=capture, rcs=rcs)


def render(inputs, data, unset="_unset"):
    fdata = data.copy()
    outputs = []
    for i in inputs:
        while True:
            try:
                outputs.append(i % fdata)
                break
            except KeyError as err:
                for key in err.args:
                    fdata[key] = unset
    return outputs

def item_data(item):
    data = {'iqn': item.iqn, 'local_path': item.get('local_path', "")}
    data.update(item.alltags)
    data['_tags'] = ' '.join(item.alltags.keys())
    return data


def group_data(group):
    data = {'iqn': group.iqn}
    data.update(group.alltags)
    data['_tags'] = ' '.join(group.alltags.keys())
    return data


def stream_data(stream, extra=None):
    if not stream:
        stream = {}
        tags = {}
    else:
        tags = stream.tags

    data = {
        'iqn': stream.get('iqn'),
        'description': stream.get('description'),
    }
    data.update(tags)
    data['_tags'] = ' '.join(tags.keys())

    if extra:
        data.update(extra)
    return data


def collection_data(collection, extra=None):
    if not collection:
        collection = {}

    data = {
        'description': collection.get('description'),
    }

    if extra:
        data.update(extra)
    return data


def check_config(config):
    missing = []
    for f in REQUIRED_FIELDS:
        if f not in config:
            missing.append(f)
    if missing:
        raise TypeError("Missing required config entries for %s" % missing)


def load_stream_output(output, reference, fmt="serial_list"):
    # parse command output and return

    if fmt == "serial_list":
        # "line" format just is a list of serials that are present
        working = reference.as_dict()
        items = []
        seen = []
        for line in output.splitlines():
            if line in seen:
                continue
            items.append({'serial': line})
            seen.append(line)

        working['item_groups'] = items
        return Stream(working)

    elif fmt == "yaml":
        return Stream(yaml.safe_load(output))

    return


def run_command(args, capture=False, rcs=None):
    if not rcs:
        rcs = [0]

    if not capture:
        stdout = None
    else:
        stdout = subprocess.PIPE

    sp = subprocess.Popen(args, stdout=stdout, shell=False)
    (out, _err) = sp.communicate()
    rc = sp.returncode

    if rc not in rcs:
        raise subprocess.CalledProcessError(rc, args)

    if out is None:
        out = ''
    return (rc, out)


def get_local_copy(reader, path, read_size=READ_SIZE):
    (tfd, tpath) = tempfile.mkstemp()
    tfile = os.fdopen(tfd, "w")
    try:
        with reader(path) as rfp:
            while True:
                buf = rfp.read(read_size)
                tfile.write(buf)
                if len(buf) != read_size:
                    break
        return (tpath, True)

    except Exception as e:
        os.unlink(tpath)
        raise e

# vi: ts=4 expandtab syntax=python

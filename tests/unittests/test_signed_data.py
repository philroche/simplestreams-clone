import shutil
import subprocess
import tempfile

from nose.tools import raises
from os.path import join
from simplestreams import mirrors
from simplestreams import objectstores
from simplestreams.util import SignatureMissingException
from tests.testutil import get_mirror_reader, EXAMPLES_DIR


def _tmp_reader():
    sstore = objectstores.FileStore(tempfile.gettempdir())
    return mirrors.ObjectStoreMirrorReader(sstore)


@raises(subprocess.CalledProcessError)
def test_read_bad_data():
    good = join(EXAMPLES_DIR, "foocloud", "streams", "v1", "index.sjson")
    bad = join(tempfile.gettempdir(), "index.sjson")
    shutil.copy(good, bad)
    with open(bad, 'r+') as f:
        lines = f.readlines()
        f.truncate()
        f.seek(0)
        for line in lines:
            f.write(line.replace('foovendor', 'attacker'))

    _tmp_reader().read_json("index.sjson")


@raises(SignatureMissingException)
def test_read_unsigned():
    # empty files aren't signed
    open(join(tempfile.gettempdir(), 'index.json'), 'w').close()

    _tmp_reader().read_json("index.json")


def test_read_signed():
    reader = get_mirror_reader("foocloud")
    reader.read_json("streams/v1/index.sjson")

import subprocess

from nose.tools import raises
from simplestreams.util import SignatureMissingException
from tests.testutil import get_mirror_reader

@raises(subprocess.CalledProcessError)
def test_read_bad_data():
    reader = get_mirror_reader("bad", signed=True)
    reader.read("index.sjson")

@raises(SignatureMissingException)
def test_read_unsigned():
    reader = get_mirror_reader("bad", signed=True)
    reader.read("index.json")

def test_read_signed():
    reader = get_mirror_reader("foocloud", signed=True)
    reader.read("streams/v1/index.sjson")

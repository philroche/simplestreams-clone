import logging
from logging import (DEBUG, ERROR, FATAL, INFO, NOTSET, WARN, WARNING)

def basicConfig(**kwargs):
    log = logging.getLogger()
    for h in log.handlers:
        log.removeHandler(h)
    logging.basicConfig(**kwargs)


basicConfig()
LOG = logging.getLogger(name='sstreams')

# vi: ts=4 expandtab syntax=python

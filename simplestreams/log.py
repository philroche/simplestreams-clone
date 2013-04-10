import logging
from logging import (DEBUG, ERROR, FATAL, INFO, NOTSET, WARN, WARNING)


class NullHandler(logging.Handler):
    def emit(self, record):
        pass


def basicConfig(**kwargs):
    # basically like logging.basicConfig but only output for our logger
    if kwargs.get('filename'):
        handler = logging.FileHandler(filename=kwargs['filename'],
                                      mode=kwargs.get('filemode', 'a'))
    elif kwargs.get('stream'):
        handler = logging.StreamHandler(stream=kwargs['stream'])
    else:
        handler = NullHandler()

    level = kwargs.get('level', NOTSET)

    handler.setFormatter(logging.Formatter(fmt=kwargs.get('format'),
                                           datefmt=kwargs.get('datefmt')))
    handler.setLevel(level)

    logging.getLogger().setLevel(level)

    logger = _getLogger()
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.setLevel(level)
    logger.addHandler(handler)

    print "HI"


def _getLogger(name='sstreams'):
    return logging.getLogger(name)


logging.basicConfig()
LOG = _getLogger()

# vi: ts=4 expandtab syntax=python

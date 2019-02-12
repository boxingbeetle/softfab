# SPDX-License-Identifier: BSD-3-Clause

from softfab.config import dbDir, loggingLevel
from softfab.version import version

import logging
import os
import os.path

def _convertLoggingLevel(level):
    if isinstance(level, int):
        return level
    else:
        # NOTE: getLevelName can also convert back to integer,
        # but that feature is not documented in the Python manual
        intLevel = logging.getLevelName(level)
        if isinstance(intLevel, int):
            return intLevel
        else:
            raise ValueError(intLevel)

if not os.path.exists(dbDir):
    os.makedirs(dbDir)

logging.basicConfig(
    level = _convertLoggingLevel(loggingLevel),
    format = '* %(asctime)s %(levelname)-8s> %(message)s',
    filename = dbDir + '/cc-log.txt', filemode = 'a'
    )

logging.info('> > Control Center startup, version %s', version)

# SPDX-License-Identifier: BSD-3-Clause

import logging
import os
import os.path

from softfab.config import dbDir
from softfab.version import VERSION

if not os.path.exists(dbDir):
    os.makedirs(dbDir)

logging.basicConfig(
    level = logging.INFO,
    format = '* %(asctime)s %(levelname)-8s> %(message)s',
    filename = dbDir + '/cc-log.txt', filemode = 'a'
    )

logging.info('> > Control Center startup, version %s', VERSION)

# SPDX-License-Identifier: BSD-3-Clause

import logging

from softfab.config import dbDir
from softfab.version import VERSION

logging.basicConfig(
    level = logging.INFO,
    format = '* %(asctime)s %(levelname)-8s> %(message)s',
    filename = dbDir + '/cc-log.txt', filemode = 'a'
    )

logging.info('> > Control Center startup, version %s', VERSION)

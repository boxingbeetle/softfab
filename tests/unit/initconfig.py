# SPDX-License-Identifier: BSD-3-Clause

import os
from softfab import config
# Set 'config.dbDir' to the current directory before importing 'initlog' to
# have the log file there rather than in 'testdb', which will be removed later
config.dbDir = '.'
import softfab.initlog
config.dbDir = 'testdb'
assert not os.path.exists(config.dbDir), 'dir already exists: ' + config.dbDir
config.dbAtomicWrites = False

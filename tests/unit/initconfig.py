# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path

from softfab import config
from softfab.initlog import initLogging


# Create log in the current directory rather than in 'testdb',
# because the latter will be removed later.
initLogging(Path.cwd())

dbDir = Path('testdb')
assert not dbDir.exists(), f'dir already exists: {dbDir}'
config.dbDir = str(dbDir)

config.dbAtomicWrites = False

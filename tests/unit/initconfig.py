# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
import os, os.path

from softfab import config
from softfab.initlog import initLogging


def removeDB():
    """Removes all database test directories."""
    _removeRec(str(config.dbDir))

def _removeRec(path):
    """Removes a directory and the files it contains, recursively."""
    if os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        for file in os.listdir(path):
            _removeRec(path + '/' + file)
        os.rmdir(path)
    else:
        assert False, path


# Create log in the current directory rather than in 'testdb',
# because the latter will be removed later.
initLogging(Path.cwd())

dbDir = Path('testdb')
assert not dbDir.exists(), f'dir already exists: {dbDir}'
config.dbDir = dbDir

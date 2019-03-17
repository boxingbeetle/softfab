# SPDX-License-Identifier: BSD-3-Clause

# Avoid calling fsync on record rewrites.
# Syncing on every file would make conversions of large databases take forever.
# The upgrade procedure states that a backup should be made before upgrading,
import sys

# so in case of abnormal termination we can just restart the upgrade from the
# backup.
from softfab import config
# Set conversion flags.
from softfab.conversionflags import (
    setConversionFlags, setConversionFlagsForVersion
)
# Check whether we can convert from the database version in use before the
# upgrade.
from softfab.projectlib import project
from softfab.utils import parseVersion

config.dbAtomicWrites = False

# pylint: disable=wrong-import-position

setConversionFlags()

try:
    versionStr = project['version']
except KeyError:
    dbVersion = 0, 0, 0
else:
    try:
        dbVersion = parseVersion(versionStr)
    except ValueError:
        dbVersion = 0, 0, 0
if dbVersion < (2, 16, 0):
    print(
        'Cannot convert database because its format is too old (%s).'
        % '.'.join(str(i) for i in dbVersion), file=sys.stderr
        )
    print(
        'Please upgrade to an earlier SoftFab version first.', file=sys.stderr
        )
    print('See release notes for details.', file=sys.stderr)
    sys.exit(1)

setConversionFlagsForVersion(dbVersion)

def convertAll() -> None:
    '''Convert all databases to the current format.
    '''

    from softfab.databases import iterDatabases
    from softfab.taskrunnerlib import recomputeRunning

    for db in iterDatabases():
        print('Converting', db.description, 'database...')
        db.convert()

    print('Recomputing running tasks...')
    recomputeRunning()

    print('Updating database version tag...')
    project.updateVersion()

    print('Done.')

# SPDX-License-Identifier: BSD-3-Clause

'''Collection of flags that control what kind of database conversions should
be applied. It is used during data migrations.

We used to keep these flags in the module they apply to, but that does not
work since some module initialisations load records from other databases,
causing them to be parsed before the flags are set up.
'''

from typing import Tuple
import logging

from click import echo, get_current_context

from softfab.utils import parseVersion
from softfab.version import VERSION
import softfab.config

# Set during any migration.
migrationInProgress = False

def setConversionFlags() -> None:
    '''Sets all conversion flags to True.
    '''
    variables = globals()
    for name in list(variables.keys()):
        if isinstance(variables[name], bool):
            variables[name] = True

def setConversionFlagsForVersion(
        version: Tuple[int, int, int] # pylint: disable=unused-argument
        ) -> None:
    '''Sets conversion flags according to the given version that we are
    converting from.
    '''

def migrateData() -> None:
    # Avoid calling fsync on record rewrites.
    # Syncing on every file would make migrations of large databases take
    # forever. The upgrade procedure states that a backup should be made
    # before upgrading, so in case of abnormal termination the user can
    # restart the upgrade from the backup.
    softfab.config.dbAtomicWrites = False

    # Set conversion flags.
    setConversionFlags()

    # Check whether we can convert from the database version in use before
    # the migration.
    from softfab.projectlib import projectDB
    projectDB.preload()
    versionStr = projectDB['singleton'].dbVersion
    try:
        dbVersion = parseVersion(versionStr)
    except ValueError as ex:
        echo(f"Failed to parse database version: {ex}\n"
             f"Migration aborted.", err=True)
        get_current_context().exit(1)
    if dbVersion < (2, 16, 0):
        echo(f"Cannot migrate database because its format "
             f"({versionStr}) is too old.\n"
             f"Please upgrade to an earlier SoftFab version first.\n"
             f"See release notes for details.", err=True)
        get_current_context().exit(1)

    setConversionFlagsForVersion(dbVersion)

    logging.info("Migrating from version %s to version %s", versionStr, VERSION)
    try:
        # Inline import to break cycle.
        from softfab.databases import convertAll
        convertAll()
    except Exception as ex:
        logging.exception("Migration aborted with error: %s", ex)
        raise
    else:
        logging.info("Migration complete")

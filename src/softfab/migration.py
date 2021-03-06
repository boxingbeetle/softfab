# SPDX-License-Identifier: BSD-3-Clause

'''Collection of flags that control what kind of database conversions should
be applied. It is used during data migrations.

We used to keep these flags in the module they apply to, but that does not
work since some module initialisations load records from other databases,
causing them to be parsed before the flags are set up.
'''

from itertools import chain
from typing import Tuple, cast
import logging

from click import echo, get_current_context

from softfab.databases import initDatabases
from softfab.joblib import JobDB
from softfab.productlib import ProductDB
from softfab.projectlib import ProjectDB
from softfab.resourcelib import ResourceDB, recomputeRunning
from softfab.taskrunlib import TaskRunDB
from softfab.utils import parseVersion
from softfab.version import VERSION
import softfab.config
import softfab.databaselib


def setConversionFlags() -> None:
    '''Sets all conversion flags to True.
    '''
    softfab.databaselib.migrationInProgress = True

def setConversionFlagsForVersion(
        version: Tuple[int, int, int] # pylint: disable=unused-argument
        ) -> None:
    '''Sets conversion flags according to the given version that we are
    converting from.
    '''

def getDataVersion() -> str:
    """Read the format version from the project data."""

    projectDB = ProjectDB(softfab.config.dbDir / 'project')
    projectDB.preload()
    return projectDB['singleton'].dbVersion

def _convertAll() -> None:
    """Convert all databases to the current format."""

    databases = initDatabases(softfab.config.dbDir)
    for db in databases.values():
        echo(f'Loading {db.description} database...')
        db.preload()
    for db in databases.values():
        echo(f'Migrating {db.description} database...')
        db.convert()

    echo('Checking for obsolete products...')
    jobDB = cast(JobDB, databases['jobDB'])
    productDB = cast(ProductDB, databases['productDB'])
    orphanedProductIDs = set(productDB.keys())
    for job in jobDB:
        for product in chain(job.getInputs(), job.getProduced()):
            orphanedProductIDs.discard(product.getId())
    if orphanedProductIDs:
        echo(f'Removing {len(orphanedProductIDs)} obsolete product(s)...')
        for productID in orphanedProductIDs:
            productDB.remove(productDB[productID])
    else:
        echo('No obsolete products found.')

    echo('Recomputing running tasks...')
    resourceDB = cast(ResourceDB, databases['resourceDB'])
    taskRunDB = cast(TaskRunDB, databases['taskRunDB'])
    recomputeRunning(resourceDB, taskRunDB)

    echo('Updating database version tag...')
    projectDB = cast(ProjectDB, databases['projectDB'])
    project = projectDB['singleton']
    project.updateVersion()

    echo('Done.')

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
    versionStr = getDataVersion()
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
        _convertAll()
    except Exception as ex:
        logging.exception("Migration aborted with error: %s", ex)
        raise
    else:
        logging.info("Migration complete")

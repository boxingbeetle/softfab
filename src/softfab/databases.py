# SPDX-License-Identifier: BSD-3-Clause

from importlib import reload
from typing import Any, Iterator, Mapping, get_type_hints

from softfab import (
    configlib, databaselib, frameworklib, joblib, productdeflib, productlib,
    projectlib, resourcelib, restypelib, schedulelib, taskdeflib, taskrunlib,
    tokens, userlib
)


# Note: The databases should be ordered such that all if D2 depends on D1,
#       D1 is positioned in the list before D2.
# TODO: Automatically order in this way, or at least detect if the order is
#       invalid.
def iterDatabases() -> Iterator[databaselib.Database]:
    yield projectlib.projectDB
    yield restypelib.resTypeDB
    yield productdeflib.productDefDB
    yield frameworklib.frameworkDB
    yield taskdeflib.taskDefDB
    yield resourcelib.resourceDB
    yield productlib.productDB
    yield joblib.jobDB # joblib must go before taskrunlib despite dependencies
    yield taskrunlib.taskRunDB
    yield configlib.configDB
    yield schedulelib.scheduleDB
    yield userlib.userDB
    yield tokens.tokenDB

def reloadDatabases() -> None:
    # !!! NOTE: The order of reloading is very important:
    # dependent modules must be reloaded AFTER their dependencies
    # TODO: Automate this.
    reload(projectlib)
    reload(tokens)
    reload(userlib)
    reload(restypelib)
    reload(productdeflib)
    reload(frameworklib)
    reload(taskdeflib)
    reload(productlib)
    reload(taskrunlib)
    reload(resourcelib)
    reload(joblib)
    reload(configlib)
    reload(schedulelib)

    for db in iterDatabases():
        db.preload()

def injectDependencies(obj: Any, dependencies: Mapping[str, object]) -> None:
    """Inject the dependencies that the given object declared."""

    isClass = isinstance(obj, type)
    for annName, annType in get_type_hints(obj).items():
        if not hasattr(obj, annName):
            if annName.startswith('_'):
                continue
            if str(annType).startswith('typing.ClassVar') != isClass:
                continue
            try:
                dep = dependencies[annName]
            except KeyError:
                qualName = (obj if isClass else obj.__class__).__qualname__
                raise NameError(f"{qualName} declares unknown value {annName}")
            else:
                setattr(obj, annName, dep)

def convertAll() -> None:
    """Convert all databases to the current format."""

    for db in iterDatabases():
        print('Migrating', db.description, 'database...')
        db.convert()

    print('Recomputing running tasks...')
    resourcelib.recomputeRunning(resourcelib.resourceDB, taskrunlib.taskRunDB)

    print('Updating database version tag...')
    projectlib.project.updateVersion()

    print('Done.')

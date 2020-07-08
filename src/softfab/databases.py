# SPDX-License-Identifier: BSD-3-Clause

from importlib import reload
from typing import Any, Iterator, Mapping, Optional, cast, get_type_hints

from softfab import (
    configlib, databaselib, frameworklib, joblib, productdeflib, productlib,
    projectlib, resourcelib, restypelib, schedulelib, taskdeflib, taskrunlib,
    tokens, userlib
)


# Note: The databases should be ordered such that all if D2 depends on D1,
#       D1 is positioned in the list before D2.
# TODO: Automatically order in this way, or at least detect if the order is
#       invalid.
def _iterDatabases() -> Iterator[databaselib.Database[Any]]:
    yield projectlib.projectDB
    yield restypelib.resTypeDB
    yield productdeflib.productDefDB
    yield frameworklib.frameworkDB
    yield taskdeflib.taskDefDB
    yield productlib.productDB
    yield joblib.jobDB # joblib must go before taskrunlib despite dependencies
    yield taskrunlib.taskRunDB
    yield resourcelib.resourceDB
    yield configlib.configDB
    yield schedulelib.scheduleDB
    yield userlib.userDB
    yield tokens.tokenDB

_databases: Optional[Mapping[str, databaselib.Database[Any]]] = None

def getDatabases() -> Mapping[str, databaselib.Database[Any]]:
    global _databases
    if _databases is None:
        databases = {}
        for db in _iterDatabases():
            name = db.__class__.__name__
            databases[name[0].lower() + name[1:]] = db
        for db in databases.values():
            injectDependencies(db.factory, databases)
        _databases = databases
    return _databases

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

    # Force mapping creation and factory injection to be redone.
    global _databases
    _databases = None
    getDatabases()

    for db in _iterDatabases():
        db.preload()

def injectDependencies(obj: Any, dependencies: Mapping[str, object]) -> None:
    """Inject the dependencies that the given object declared."""

    isClass = isinstance(obj, type)
    cls = obj if isClass else obj.__class__
    for annName, annType in get_type_hints(cls).items():
        if not hasattr(obj, annName):
            if annName.startswith('_'):
                continue
            if str(annType).startswith('typing.ClassVar') != isClass:
                continue
            try:
                dep = dependencies[annName]
            except KeyError:
                qualName = cls.__qualname__
                raise NameError(f"{qualName} declares unknown value {annName}")
            else:
                setattr(obj, annName, dep)

def convertAll() -> None:
    """Convert all databases to the current format."""

    databases = getDatabases()
    for db in databases.values():
        print('Loading', db.description, 'database...')
        if not isinstance(db, projectlib.ProjectDB):
            db.preload()
    for db in databases.values():
        print('Migrating', db.description, 'database...')
        db.convert()

    print('Recomputing running tasks...')
    resourceDB = cast(resourcelib.ResourceDB, databases['resourceDB'])
    taskRunDB = cast(taskrunlib.TaskRunDB, databases['taskRunDB'])
    resourcelib.recomputeRunning(resourceDB, taskRunDB)

    print('Updating database version tag...')
    projectDB = cast(projectlib.ProjectDB, databases['projectDB'])
    project = projectDB['singleton']
    project.updateVersion()

    print('Done.')

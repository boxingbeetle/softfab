# SPDX-License-Identifier: BSD-3-Clause

from importlib import reload
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, get_type_hints

from softfab import (
    configlib, databaselib, frameworklib, joblib, productdeflib, productlib,
    projectlib, resourcelib, restypelib, schedulelib, taskdeflib, taskrunlib,
    tokens, userlib
)
from softfab.resultlib import ResultStorage


# Note: The databases should be ordered such that all if D2 depends on D1,
#       D1 is positioned in the list before D2.
# TODO: Automatically order in this way, or at least detect if the order is
#       invalid.
def _iterDatabases(dbDir: Path) -> Iterator[databaselib.Database[Any]]:
    yield projectlib.ProjectDB(dbDir / 'project')
    yield tokens.TokenDB(dbDir / 'tokens')
    yield restypelib.resTypeDB
    yield productdeflib.productDefDB
    yield frameworklib.frameworkDB
    yield taskdeflib.taskDefDB
    yield productlib.ProductDB(dbDir / 'products')
    yield joblib.jobDB # joblib must go before taskrunlib despite dependencies
    yield taskrunlib.TaskRunDB(dbDir / 'taskruns')
    yield resourcelib.resourceDB
    yield configlib.configDB
    yield schedulelib.ScheduleDB(dbDir / 'scheduled')
    yield userlib.UserDB(dbDir / 'users')

def initDatabases(dbDir: Path) -> Mapping[str, databaselib.Database[Any]]:
    databases = {}
    factories = {}
    for db in _iterDatabases(dbDir):
        name = db.__class__.__name__
        dbName = name[0].lower() + name[1:]
        assert dbName not in databases
        databases[dbName] = db
        assert name.endswith('DB'), name
        factoryName = f'{name[0].lower()}{name[1:-2]}Factory'
        assert factoryName not in factories
        factories[factoryName] = db.factory
    dependencies: Dict[str, object] = dict(databases)
    dependencies.update(factories)
    dependencies['resultStorage'] = ResultStorage(dbDir / 'results')
    for factory in factories.values():
        injectDependencies(factory, dependencies)
    return databases

def reloadDatabases(dbDir: Path) -> Mapping[str, databaselib.Database[Any]]:
    # !!! NOTE: The order of reloading is very important:
    # dependent modules must be reloaded AFTER their dependencies
    # TODO: Automate this.
    reload(restypelib)
    reload(productdeflib)
    reload(frameworklib)
    reload(taskdeflib)
    reload(resourcelib)
    reload(joblib)
    reload(configlib)

    # Force mapping creation and factory injection to be redone.
    databases = initDatabases(dbDir)

    for db in databases.values():
        db.preload()

    return databases

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

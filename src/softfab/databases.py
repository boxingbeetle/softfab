# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, get_type_hints

from softfab.configlib import ConfigDB
from softfab.databaselib import Database
from softfab.frameworklib import FrameworkDB
from softfab.joblib import JobDB
from softfab.productdeflib import ProductDefDB
from softfab.productlib import ProductDB
from softfab.projectlib import ProjectDB
from softfab.resourcelib import ResourceDB
from softfab.restypelib import ResTypeDB
from softfab.resultlib import ResultStorage
from softfab.schedulelib import ScheduleDB
from softfab.taskdeflib import TaskDefDB
from softfab.taskrunlib import TaskRunDB
from softfab.tokens import TokenDB
from softfab.userlib import UserDB


def _iterDatabases(dbDir: Path) -> Iterator[Database[Any]]:
    yield ProjectDB(dbDir / 'project')
    yield TokenDB(dbDir / 'tokens')
    yield ResTypeDB(dbDir / 'restypes')
    yield ProductDefDB(dbDir / 'productdefs')
    yield FrameworkDB(dbDir / 'frameworks')
    yield TaskDefDB(dbDir / 'taskdefs')
    yield ProductDB(dbDir / 'products')
    yield JobDB(dbDir / 'jobs')
    yield TaskRunDB(dbDir / 'taskruns')
    yield ResourceDB(dbDir / 'resources')
    yield ConfigDB(dbDir / 'configs')
    yield ScheduleDB(dbDir / 'scheduled')
    yield UserDB(dbDir / 'users')

def initDatabases(dbDir: Path) -> Mapping[str, Database[Any]]:
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
    dependencies['artifactsPath'] = dbDir / 'artifacts'
    for factory in factories.values():
        injectDependencies(factory, dependencies)
    return databases

def reloadDatabases(dbDir: Path) -> Mapping[str, Database[Any]]:
    """Called by unit tests to reload the databases from disk."""
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

# SPDX-License-Identifier: BSD-3-Clause

from softfab import (
    projectlib, restypelib, resourcelib, productdeflib, frameworklib,
    taskdeflib, storagelib, shadowlib, taskrunnerlib, productlib, joblib,
    taskrunlib, configlib, schedulelib, userlib
    )

from importlib import reload

# Note: The databases should be ordered such that all if D2 depends on D1,
#       D1 is positioned in the list before D2.
# TODO: Automatically order in this way, or at least detect if the order is
#       invalid.
def iterDatabases():
    yield projectlib._projectDB # pylint: disable=protected-access
    yield restypelib.resTypeDB
    yield resourcelib.resourceDB
    yield productdeflib.productDefDB
    yield frameworklib.frameworkDB
    yield taskdeflib.taskDefDB
    yield storagelib.storageDB
    yield shadowlib.shadowDB
    yield taskrunnerlib.taskRunnerDB
    yield productlib.productDB
    yield joblib.jobDB # joblib must go before taskrunlib despite dependencies
    yield taskrunlib.taskRunDB
    yield configlib.configDB
    yield schedulelib.scheduleDB
    yield userlib.userDB

def iterDatabasesToPreload():
    for db in iterDatabases():
        if db.alwaysInMemory:
            yield db

def reloadDatabases():
    # !!! NOTE: The order of reloading is very important:
    # dependent modules must be reloaded AFTER their dependencies
    # TODO: Automate this.
    reload(userlib)
    reload(restypelib)
    reload(resourcelib)
    reload(storagelib)
    reload(productdeflib)
    reload(frameworklib)
    reload(taskdeflib)
    reload(productlib)
    reload(shadowlib)
    reload(taskrunlib)
    reload(joblib)
    reload(configlib)
    reload(schedulelib)
    # There are a circular dependencies between joblib, shadowlib, taskrunlib
    # and taskrunnerlib.
    # Reloading taskrunnerlib last is needed to make the RunObservers work,
    # without this a Task Runner will not know it is busy.
    reload(taskrunnerlib)

    for db in iterDatabasesToPreload():
        db.preload()

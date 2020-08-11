# SPDX-License-Identifier: BSD-3-Clause

from io import StringIO

from pytest import fixture, mark
import attr

# Import for the side effect of setting dbDir.
# We're not going to use that dir, but the modules under test still need it.
import initconfig

from softfab.joblib import JobDB
from softfab.resourcelib import (
    RequestFactory, ResourceDB, TaskRunner, TaskRunnerData
)
from softfab.resourceview import getResourceStatus
from softfab.restypelib import ResTypeDB
from softfab.timelib import setTime
from softfab.tokens import TokenDB
from softfab.taskrunlib import TaskRunDB
from softfab.xmlbind import parse


class Databases:

    def __init__(self, dbDir):
        self.dbDir = dbDir
        self.reload()

    def reload(self):
        dbDir = self.dbDir

        self.jobDB = JobDB(dbDir / 'jobs')
        self.resTypeDB = ResTypeDB(dbDir / 'restypes')
        self.taskRunDB = TaskRunDB(dbDir / 'taskruns')
        self.resourceDB = ResourceDB(dbDir / 'resources')
        self.tokenDB = TokenDB(dbDir / 'tokens')

        # TODO: Use the generic injection system.
        self.resourceDB.factory.resTypeDB = self.resTypeDB
        self.resourceDB.factory.taskRunDB = self.taskRunDB
        self.resourceDB.factory.tokenDB = self.tokenDB

        self.jobDB.preload()
        self.resTypeDB.preload()
        self.taskRunDB.preload()
        self.resourceDB.preload()

@fixture
def databases(tmp_path):
    ret = Databases(tmp_path)
    assert len(ret.resourceDB) == 0
    return ret

dataRun = parse(RequestFactory(), StringIO(
    '<request runnerVersion="2.0.0" host="factorypc">'
        '<run jobId="2004-05-06_12-34_567890" taskId="TC-6.1" runId="0"/>'
    '</request>'
    ))

dataNoRun = parse(RequestFactory(), StringIO(
    '<request runnerVersion="2.0.0" host="factorypc">'
    '</request>'
    ))

@mark.parametrize('data1', (dataRun, dataNoRun))
@mark.parametrize('data2', (dataRun, dataNoRun))
def testTaskRunnerSync(databases, data1, data2):
    """Test syncing of the TR database."""

    def check():
        """Check if cache and database are in sync."""
        databases.reload()
        record2 = databases.resourceDB[record1.getId()]
        del record2._properties['tokenId']
        assert record1._properties == record2._properties

    resourceFactory = databases.resourceDB.factory
    record1 = resourceFactory.newTaskRunner('runner1', '', set())
    databases.resourceDB.add(record1)
    record1.sync(databases.jobDB, data1)
    check()

    # Change data in database.
    record1.sync(databases.jobDB, data2)
    check()

@mark.parametrize('data', (dataRun, dataNoRun))
def testTaskRunnerSuspend(databases, data):
    """Test suspend functionality."""

    resourceFactory = databases.resourceDB.factory
    record = resourceFactory.newTaskRunner('runner1', '', set())
    record.sync(databases.jobDB, data)

    # Check if initially not suspended.
    assert not record.isSuspended()
    # Check False -> True transition of suspended.
    record.setSuspend(True, None)
    assert record.isSuspended()
    # Check True -> True transition of suspended.
    record.setSuspend(True, None)
    assert record.isSuspended()
    # Check True -> False transition of suspended.
    record.setSuspend(False, None)
    assert not record.isSuspended()
    # Check False -> False transition of suspended.
    record.setSuspend(False, None)
    assert not record.isSuspended()

def testTaskRunnerStatus(databases):
    """Test if right status is returned."""

    # Idle TR.
    data = dataNoRun
    busy = False

# TODO: The old design of resourcelib made the Task Runner the authority that
#       determines whether a task is running. In the new design, it is the
#       Control Center who is authorative. Because of this, it is not possible
#       to create a Task Runner record in busy state without filling all other
#       databases with valid data as well. But if we do that, it's like creating
#       a second joblib test. Instead, I kept the resourcelib test simple
#       and disabled this test case. However, it means that parts of the
#       functionality remain untested, which is not a good situation.
#    data = dataRun
#    busy = True

    setTime(1000) # time at moment of record creation
    resourceFactory = databases.resourceDB.factory
    record = resourceFactory.newTaskRunner('runner1', '', set())
    databases.resourceDB.add(record)
    record.sync(databases.jobDB, data)
    #record.getSyncWaitDelay = lambda: 3
    record.getWarnTimeout = lambda: 8
    record.getLostTimeout = lambda: 35

    # Check if status 'lost' is returned if the time since last sync has
    # become larger than the lost timeout value (= 35):
    setTime(1036) # - 1000 > 35
    assert getResourceStatus(record) == 'lost'
    # Check that pausing the TR doesn't change this status:
    record.setSuspend(True, None)
    assert getResourceStatus(record) == 'lost'
    record.setSuspend(False, None)
    assert getResourceStatus(record) == 'lost'
    # Check if status 'warning' is returned if the time since last sync has
    # become larger than the warning timeout value (= 8)
    # but smaller than the lost timeout value (= 35):
    setTime(1035) # - 1000 > 8
    assert getResourceStatus(record) == 'warning'
    setTime(1009) # - 1000 > 8
    assert getResourceStatus(record) == 'warning'
    # Check that pausing the TR doesn't change this status:
    record.setSuspend(True, None)
    assert getResourceStatus(record) == 'warning'
    record.setSuspend(False, None)
    assert getResourceStatus(record) == 'warning'

    # busy or not busy dependend block:
    if busy:
        resultNotSuspended = 'busy'
        resultSuspended = 'busy'
    else:
        resultNotSuspended = 'free'
        resultSuspended = 'suspended'
    # Check the status if the time since last sync has become
    # not larger than the warning timeout value (= 8).
    # If TR is busy, 'busy' should be returned.
    # If TR is not busy, 'free' should be returned.
    setTime(1008) # - 1000 == 8
    assert getResourceStatus(record) == resultNotSuspended
    # Check that pausing the TR returns 'busy', in case TR is busy,
    # or returns 'suspended' in case TR is not busy:
    record.setSuspend(True, None)
    assert getResourceStatus(record) == resultSuspended
    # Check that unpausing the TR returns 'busy', in case TR is busy,
    # or returns 'free' in case TR is not busy:
    record.setSuspend(False, None)
    assert getResourceStatus(record) == resultNotSuspended

    # Check if status 'unknown' is returned after a cache flush:
    databases.reload()
    record = databases.resourceDB[record.getId()]
    assert getResourceStatus(record) == 'unknown'
    # Check that (un)pausing the TR changes the status:
    record.setSuspend(True, None)
    assert getResourceStatus(record) == 'suspended'
    record.setSuspend(False, None)
    assert getResourceStatus(record) == 'unknown'

class DataFactory:
    """Factory for TaskRunnerData class.

    This is like RequestFactory, but with a different tag name.
    """

    def createData(self, attributes):
        return TaskRunnerData(attributes)

@attr.s(auto_attribs=True, frozen=True)
class TaskRunnerFactory:
    """Factory for TaskRunner resources that does not create a token."""

    databases: Databases

    def createTaskrunner(self, attributes):
        resTypeDB = self.databases.resTypeDB
        taskRunDB = self.databases.taskRunDB
        return TaskRunner(attributes, resTypeDB, taskRunDB, None)

@mark.parametrize('data', (dataRun, dataNoRun))
def testTaskRunnerToXML(databases, data):
    """Test toXML() functionality.

    Check if toXML() generates valid XML code by parsing the toXML()
    output while creating a new object and compare the old and new object,
    as well as their toXML() outputs.
    """

    # TaskRunnerData class:
    data2 = parse(DataFactory(), StringIO(data.toXML().flattenXML()))
    assert data == data2
    # TaskRunner class:
    resourceFactory = databases.resourceDB.factory
    record1 = resourceFactory.newTaskRunner('runner1', '', set())
    record1.sync(databases.jobDB, data)
    taskRunnerFactory = TaskRunnerFactory(databases)
    record2 = parse(taskRunnerFactory, StringIO(record1.toXML().flattenXML()))
    assert record1._properties == record2._properties

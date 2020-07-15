# SPDX-License-Identifier: BSD-3-Clause

import unittest
from importlib import reload
from io import StringIO

from initconfig import removeDB

from softfab import joblib, resourcelib, restypelib, xmlbind
from softfab.databases import reloadDatabases
from softfab.resourceview import getResourceStatus
from softfab.timelib import setTime


class DataFactory:
    """Factory for TaskRunnerData class."""
    def createData(self, attributes):
        return resourcelib.TaskRunnerData(attributes)

class TaskRunnerFactory:
    """Factory for TaskRunner resources that does not create a token."""
    def createTaskrunner(self, attributes):
        return resourcelib.TaskRunner(attributes, restypelib.resTypeDB, None)

class TestTRDatabase(unittest.TestCase):
    """Test basic Task Runner database functionality."""

    dataRun = xmlbind.parse(resourcelib.RequestFactory(), StringIO(
        '<request runnerVersion="2.0.0" host="factorypc">'
            '<run jobId="2004-05-06_12-34_567890" taskId="TC-6.1" runId="0"/>'
        '</request>'
        ))
    dataNoRun = xmlbind.parse(resourcelib.RequestFactory(), StringIO(
        '<request runnerVersion="2.0.0" host="factorypc">'
        '</request>'
        ))

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)

    def setUp(self):
        reloadDatabases()
        assert len(resourcelib.resourceDB) == 0

    def tearDown(self):
        removeDB()

    def suspendTest(self, data):
        """Test suspend functionality."""
        resourceFactory = resourcelib.resourceDB.factory
        record = resourceFactory.newTaskRunner('runner1', '', set())
        record.sync(joblib.jobDB, data)

        # Check if initially not suspended.
        self.assertTrue(not record.isSuspended())
        # Check False -> True transition of suspended.
        record.setSuspend(True, None)
        self.assertTrue(record.isSuspended())
        # Check True -> True transition of suspended.
        record.setSuspend(True, None)
        self.assertTrue(record.isSuspended())
        # Check True -> False transition of suspended.
        record.setSuspend(False, None)
        self.assertTrue(not record.isSuspended())
        # Check False -> False transition of suspended.
        record.setSuspend(False, None)
        self.assertTrue(not record.isSuspended())

    def syncTest(self, data1, data2):
        """Test syncing of the TR database."""
        resourceFactory = resourcelib.resourceDB.factory
        record1 = resourceFactory.newTaskRunner('runner1', '', set())
        resourcelib.resourceDB.add(record1)
        record1.sync(joblib.jobDB, data1)

        # Check if cache and database are in sync:
        reloadDatabases()
        record2 = resourcelib.resourceDB[record1.getId()]
        del record2._properties['tokenId']
        self.assertEqual(record1._properties, record2._properties)
        # Change data in database.
        # Check if cache and database are still in sync:
        record1.sync(joblib.jobDB, data2)
        reloadDatabases()
        record2 = resourcelib.resourceDB[record1.getId()]
        del record2._properties['tokenId']
        self.assertEqual(record1._properties, record2._properties)

    def statusTest(self, data, busy):
        """Test if right status is returned."""
        setTime(1000) # time at moment of record creation
        resourceFactory = resourcelib.resourceDB.factory
        record = resourceFactory.newTaskRunner('runner1', '', set())
        resourcelib.resourceDB.add(record)
        record.sync(joblib.jobDB, data)
        #record.getSyncWaitDelay = lambda: 3
        record.getWarnTimeout = lambda: 8
        record.getLostTimeout = lambda: 35

        # Check if status 'lost' is returned if the time since last sync has
        # become larger than the lost timeout value (= 35):
        setTime(1036) # - 1000 > 35
        self.assertEqual(getResourceStatus(record), 'lost')
        # Check that pausing the TR doesn't change this status:
        record.setSuspend(True, None)
        self.assertEqual(getResourceStatus(record), 'lost')
        record.setSuspend(False, None)
        self.assertEqual(getResourceStatus(record), 'lost')
        # Check if status 'warning' is returned if the time since last sync has
        # become larger than the warning timeout value (= 8)
        # but smaller than the lost timeout value (= 35):
        setTime(1035) # - 1000 > 8
        self.assertEqual(getResourceStatus(record), 'warning')
        setTime(1009) # - 1000 > 8
        self.assertEqual(getResourceStatus(record), 'warning')
        # Check that pausing the TR doesn't change this status:
        record.setSuspend(True, None)
        self.assertEqual(getResourceStatus(record), 'warning')
        record.setSuspend(False, None)
        self.assertEqual(getResourceStatus(record), 'warning')

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
        self.assertEqual(getResourceStatus(record), resultNotSuspended)
        # Check that pausing the TR returns 'busy', in case TR is busy,
        # or returns 'suspended' in case TR is not busy:
        record.setSuspend(True, None)
        self.assertEqual(getResourceStatus(record), resultSuspended)
        # Check that unpausing the TR returns 'busy', in case TR is busy,
        # or returns 'free' in case TR is not busy:
        record.setSuspend(False, None)
        self.assertEqual(getResourceStatus(record), resultNotSuspended)

        # Check if status 'unknown' is returned after a cache flush:
        reloadDatabases()
        record = resourcelib.resourceDB[record.getId()]
        self.assertEqual(getResourceStatus(record), 'unknown')
        # Check that (un)pausing the TR changes the status:
        record.setSuspend(True, None)
        self.assertEqual(getResourceStatus(record), 'suspended')
        record.setSuspend(False, None)
        self.assertEqual(getResourceStatus(record), 'unknown')

    def toXMLTest(self, data):
        '''Test toXML functionality.
        Check if toXML() generates valid XML code by parsing the toXML()
        output while creating a new object and compare the old and new object,
        as well as their toXML() outputs.
        '''

        # TaskRunnerData class:
        data2 = xmlbind.parse(
            DataFactory(), StringIO(data.toXML().flattenXML())
            )
        self.assertEqual(data, data2)
        # TaskRunner class:
        resourceFactory = resourcelib.resourceDB.factory
        record1 = resourceFactory.newTaskRunner('runner1', '', set())
        record1.sync(joblib.jobDB, data)
        record2 = xmlbind.parse(
            TaskRunnerFactory(),
            StringIO(record1.toXML().flattenXML())
            )
        self.assertEqual(record1._properties, record2._properties)

    def test0010sync(self):
        """Test syncing from a busy TR to an idle TR."""
        self.syncTest(self.dataRun, self.dataNoRun)

    def test0015sync(self):
        """Test syncing from an idle TR to a busy TR."""
        self.syncTest(self.dataNoRun, self.dataRun)

    def test0020suspend(self):
        """Test suspend functionality while TR is busy."""
        self.suspendTest(self.dataRun)

    def test0025suspend(self):
        """Test suspend functionality while TR is not busy."""
        self.suspendTest(self.dataNoRun)

# TODO: The old design of resourcelib made the Task Runner the authority that
#       determines whether a task is running. In the new design, it is the
#       Control Center who is authorative. Because of this, it is not possible
#       to create a Task Runner record in busy state without filling all other
#       databases with valid data as well. But if we do that, it's like creating
#       a second joblib test. Instead, I kept the resourcelib test simple
#       and disabled this test case. However, it means that parts of the
#       functionality remain untested, which is not a good situation.
#    def test0030status(self):
#        """Test status reproduction of a busy TR."""
#        self.statusTest(self.dataRun, True)

    def test0035status(self):
        """Test status reproduction of an idle TR."""
        self.statusTest(self.dataNoRun, False)

    def test0040toXML(self):
        """Test XML generation of objects of a busy TR."""
        self.toXMLTest(self.dataRun)

    def test0045toXML(self):
        """Test XML generation of objects of an idle TR."""
        self.toXMLTest(self.dataNoRun)

if __name__ == '__main__':
    unittest.main()

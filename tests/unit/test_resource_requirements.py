# SPDX-License-Identifier: BSD-3-Clause

import unittest

from initconfig import dbDir, removeDB

from softfab import databases
from softfab import configlib, resourcelib, restypelib
from softfab.resreq import taskRunnerResourceRefName
from softfab.restypelib import taskRunnerResourceTypeName
from softfab.resultcode import ResultCode
from softfab.timelib import setTime

from datageneratorlib import DataGenerator


OWNER = 'Maggy'

class TestResourceRequirements(unittest.TestCase):
    """Test resource requirements functionality.

    Every test case checks both the in-memory database (same db object on which
    operations were performed) and the on-disk database (used to load data
    after reloadDatabases() call is performed).
    """

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)
        self.jobId = 'job1'

        # Stop time, so Task Runner will not get out of sync.
        setTime(1000)

    def setUp(self):
        self.reloadDatabases()

    def tearDown(self):
        removeDB()

    def reloadDatabases(self):
        databases.reloadDatabases(dbDir)

    def runWithReload(self, config, verifyFunc):
        configId = config.getId()
        verifyFunc(config)
        self.reloadDatabases()
        config = configlib.configDB[configId]
        verifyFunc(config)

    def checkResourceClaim(self, correctSpecs, claim):
        specsByRef = {}
        for spec in claim:
            ref = spec.reference
            value = (spec.typeName, spec.capabilities)
            self.assertNotIn(ref, specsByRef) # ref must be unique
            specsByRef[ref] = value

        for ref, resTypeName, capabilities in sorted(correctSpecs):
            self.assertIn(ref, specsByRef)
            checkType, checkCaps = specsByRef.pop(ref)
            self.assertEqual(checkType, resTypeName)
            self.assertCountEqual(checkCaps, capabilities)

        self.assertCountEqual(specsByRef, ())

    def reserveResource(self, name):
        resource = resourcelib.resourceDB[name]
        self.assertFalse(resource.isReserved())
        resource.reserve('someone')
        self.assertTrue(resource.isReserved())

    def freeResource(self, name):
        resource = resourcelib.resourceDB[name]
        self.assertTrue(resource.isReserved())
        resource.free()
        self.assertFalse(resource.isReserved())

    def test0100FromTaskDef(self):
        """Test whether a simple resource requirement from the task definition
        is applied to a task."""

        def check(config):
            job, = config.createJobs(OWNER)

            task = job.getTask('task')
            self.checkResourceClaim(specs, task.resourceClaim)

        gen = DataGenerator()
        resType = gen.createResourceType(pertask=True)
        specs = (
            ('ref', resType, ('cap_a', 'cap_b')),
            (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
            )
        framework = gen.createFramework('fw', resources=())
        gen.createTask('task', framework, resources=specs)
        config = gen.createConfiguration()
        self.runWithReload(config, check)

    def test0110FromFrameworkDef(self):
        """Test whether a simple resource requirement from the framework
        definition is applied to a task."""

        def check(config):
            job, = config.createJobs(OWNER)

            task = job.getTask('task')
            self.checkResourceClaim(specs, task.resourceClaim)

        gen = DataGenerator()
        resType = gen.createResourceType(pertask=True)
        specs = (
            ('ref', resType, ('cap_a', 'cap_b')),
            (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
            )
        framework = gen.createFramework('fw', resources=specs)
        gen.createTask('task', framework, resources=())
        config = gen.createConfiguration()
        self.runWithReload(config, check)

    def test0120FromCombinedDefs(self):
        """Test whether a simple resource requirements from both the framework
        and task definitions are applied to a task."""

        def check(config):
            job, = config.createJobs(OWNER)

            task = job.getTask('task')
            self.checkResourceClaim(specs, task.resourceClaim)

        gen = DataGenerator()
        resType = gen.createResourceType(pertask=True)
        fwSpecs = (
            ('ref', resType, ('cap_a', )),
            ('ref2', resType, ('cap_c', )),
            (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
            )
        framework = gen.createFramework('fw', resources=fwSpecs)
        tdSpecs = (
            ('ref', resType, ('cap_b', )),
            ('ref3', resType, ('cap_d', )),
            )
        gen.createTask('task', framework, resources=tdSpecs)
        config = gen.createConfiguration()
        specs = (
            ('ref', resType, ('cap_a', 'cap_b')),
            ('ref2', resType, ('cap_c', )),
            ('ref3', resType, ('cap_d', )),
            (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
            )
        self.runWithReload(config, check)

    def test0130ConflictingDefs(self):
        """Test what happens if resource requirements from the framework
        and task definitions disagree about a resource's type.
        While we don't allow changing an inherted resource type when editing
        a task definition, there can be a conflict if the type is changed
        in the framework definition later.
        """

        def check(config):
            job, = config.createJobs(OWNER)

            task = job.getTask('task')
            self.checkResourceClaim(specs, task.resourceClaim)

        gen = DataGenerator()
        resType1 = gen.createResourceType(pertask=True)
        resType2 = gen.createResourceType(pertask=True)
        fwSpecs = (
            ('ref', resType1, ('cap_a', )),
            (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
            )
        framework = gen.createFramework('fw', resources=fwSpecs)
        tdSpecs = (
            ('ref', resType2, ('cap_b', )),
            )
        gen.createTask('task', framework, resources=tdSpecs)
        config = gen.createConfiguration()
        specs = (
            ('ref', resType2, ('cap_b', )),
            (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
            )
        self.runWithReload(config, check)

    def test0200AssignCombinedDefs(self):
        """Test whether simple resource requirements from both the framework
        and task definition are used in task assignment."""

        def check(config):
            job, = config.createJobs(OWNER)
            taskRunner = resourcelib.resourceDB[tr]

            # Try to assign with both cap_a and cap_b unavailable.
            self.reserveResource(resA)
            self.reserveResource(resB)
            task = job.assignTask(taskRunner)
            self.assertIsNone(task)

            # Try to assign with only cap_a unavailable.
            self.freeResource(resB)
            task = job.assignTask(taskRunner)
            self.assertIsNone(task)

            # Try to assign with only cap_b unavailable.
            self.freeResource(resA)
            self.reserveResource(resB)
            task = job.assignTask(taskRunner)
            self.assertIsNone(task)

            # Try to assign with cap_a and cap_b available.
            self.freeResource(resB)
            task = job.assignTask(taskRunner)
            self.assertIsNotNone(task)
            self.assertFalse(resourcelib.resourceDB[resA].isFree())
            self.assertFalse(resourcelib.resourceDB[resB].isFree())
            self.assertTrue(resourcelib.resourceDB[resC].isFree())
            job.taskDone('task', ResultCode.OK, 'summary text', (), {})
            self.assertTrue(resourcelib.resourceDB[resA].isFree())
            self.assertTrue(resourcelib.resourceDB[resB].isFree())
            self.assertTrue(resourcelib.resourceDB[resC].isFree())

        gen = DataGenerator()
        resType = gen.createResourceType(pertask=True)
        resA = gen.createResource(resType, ('cap_a', ))
        resB = gen.createResource(resType, ('cap_b', 'cap_d'))
        resC = gen.createResource(resType, ('cap_c', ))
        tr = gen.createTaskRunner()

        fwSpecs = (
            ('ref1', resType, ('cap_a', )),
            (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
            )
        framework = gen.createFramework('fw', resources=fwSpecs)
        tdSpecs = (
            ('ref2', resType, ('cap_b', )),
            )
        gen.createTask('task', framework, resources=tdSpecs)
        config = gen.createConfiguration()
        self.runWithReload(config, check)

    def test0210AssignNonExclusive(self):
        """Test assigning task using a non-exclusive resource."""

        def check(config):
            job, = config.createJobs(OWNER)
            taskRunner = resourcelib.resourceDB[tr]

            # Try to assign with resource unavailable.
            self.reserveResource(res)
            task = job.assignTask(taskRunner)
            self.assertIsNone(task)

            # Try to assign with resource available.
            self.freeResource(res)
            task = job.assignTask(taskRunner)
            self.assertIsNotNone(task)
            self.assertTrue(resourcelib.resourceDB[res].isFree())
            job.taskDone('task', ResultCode.OK, 'summary text', (), {})
            self.assertTrue(resourcelib.resourceDB[res].isFree())

        gen = DataGenerator()
        resType = gen.createResourceType()
        res = gen.createResource(resType, ())
        tr = gen.createTaskRunner()

        fwSpecs = (
            ('ref', resType, ()),
            (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
            )
        framework = gen.createFramework('fw', resources=fwSpecs)
        gen.createTask('task', framework, resources=())
        config = gen.createConfiguration()
        self.runWithReload(config, check)

    def test1000TestResTypeConflict(self):
        """Test configuration using different types for same reference."""

        def checkConsistent(config):
            self.assertTrue(config.isConsistent(restypelib.resTypeDB))
        def checkInconsistent(config):
            self.assertFalse(config.isConsistent(restypelib.resTypeDB))

        gen = DataGenerator()
        resTypeA = gen.createResourceType(pertask=True)
        resTypeB = gen.createResourceType(pertask=True)

        fwSpecs = (
            (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
            )
        framework = gen.createFramework('fw', resources=fwSpecs)
        tdASpecs = (
            ('ref', resTypeA, ()),
            )
        gen.createTask('taskA', framework, resources=tdASpecs)
        tdBSpecs = (
            ('ref', resTypeB, ()),
            )
        gen.createTask('taskB', framework, resources=tdBSpecs)
        config = gen.createConfiguration()

        # Both resource types are per-task, so no conflict.
        self.runWithReload(config, checkConsistent)
        # Update resource type A to be also per-job exclusive.
        restypelib.resTypeDB.update(
            restypelib.ResType.create(resTypeA, True, True)
            )
        self.runWithReload(config, checkConsistent)
        # Update resource type B to be also per-job exclusive.
        restypelib.resTypeDB.update(
            restypelib.ResType.create(resTypeB, True, True)
            )
        self.runWithReload(config, checkInconsistent)

    def test2000TestDoubleReserve(self):
        """Test reserving the same resource twice."""
        gen = DataGenerator()
        resType = gen.createResourceType()
        res = gen.createResource(resType)

        self.reserveResource(res)
        resource = resourcelib.resourceDB[res]
        with self.assertLogs(level='ERROR'):
            resource.reserve('twice')
        self.assertTrue(resource.isReserved())

    def test2010TestDoubleFree(self):
        """Test freeing the same resource twice."""
        gen = DataGenerator()
        resType = gen.createResourceType()
        res = gen.createResource(resType)

        self.reserveResource(res)
        self.freeResource(res)
        resource = resourcelib.resourceDB[res]
        with self.assertLogs(level='ERROR'):
            resource.free()
        self.assertFalse(resource.isReserved())

if __name__ == '__main__':
    unittest.main()

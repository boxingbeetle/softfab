# SPDX-License-Identifier: BSD-3-Clause

"""Test resource requirements functionality.

Every test case checks both the in-memory database (same db object on which
operations were performed) and the on-disk database (used to load data
after reloadDatabases() call is performed).
"""

from softfab.resreq import taskRunnerResourceRefName
from softfab.restypelib import ResType, taskRunnerResourceTypeName
from softfab.resultcode import ResultCode

from datageneratorlib import DataGenerator


OWNER = 'Maggy'

def checkResourceClaim(correctSpecs, claim):
    specsByRef = {}
    for spec in claim:
        ref = spec.reference
        value = (spec.typeName, spec.capabilities)
        assert ref not in specsByRef # ref must be unique
        specsByRef[ref] = value

    for ref, resTypeName, capabilities in sorted(correctSpecs):
        assert ref in specsByRef
        checkType, checkCaps = specsByRef.pop(ref)
        assert checkType == resTypeName
        assert checkCaps == set(capabilities)

    assert not specsByRef

def reserveResource(resourceDB, name):
    resource = resourceDB[name]
    assert not resource.isReserved()
    resource.reserve('someone')
    assert resource.isReserved()

def freeResource(resourceDB, name):
    resource = resourceDB[name]
    assert resource.isReserved()
    resource.free()
    assert not resource.isReserved()

def runWithReload(databases, config, verifyFunc):
    configId = config.getId()
    verifyFunc(config)
    databases.reload()
    config = databases.configDB[configId]
    verifyFunc(config)

def testResReqFromTaskDef(databases):
    """Test whether a simple resource requirement from the task definition
    is applied to a task."""

    def check(config):
        job, = config.createJobs(OWNER)

        task = job.getTask('task')
        checkResourceClaim(specs, task.resourceClaim)

    gen = DataGenerator(databases)
    resType = gen.createResourceType(pertask=True)
    specs = (
        ('ref', resType, ('cap_a', 'cap_b')),
        (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
        )
    framework = gen.createFramework('fw', resources=())
    gen.createTask('task', framework, resources=specs)
    config = gen.createConfiguration()
    runWithReload(databases, config, check)

def testResReqFromFrameworkDef(databases):
    """Test whether a simple resource requirement from the framework
    definition is applied to a task."""

    def check(config):
        job, = config.createJobs(OWNER)

        task = job.getTask('task')
        checkResourceClaim(specs, task.resourceClaim)

    gen = DataGenerator(databases)
    resType = gen.createResourceType(pertask=True)
    specs = (
        ('ref', resType, ('cap_a', 'cap_b')),
        (taskRunnerResourceRefName, taskRunnerResourceTypeName, ()),
        )
    framework = gen.createFramework('fw', resources=specs)
    gen.createTask('task', framework, resources=())
    config = gen.createConfiguration()
    runWithReload(databases, config, check)

def testResReqFromCombinedDefs(databases):
    """Test whether a simple resource requirements from both the framework
    and task definitions are applied to a task."""

    def check(config):
        job, = config.createJobs(OWNER)

        task = job.getTask('task')
        checkResourceClaim(specs, task.resourceClaim)

    gen = DataGenerator(databases)
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
    runWithReload(databases, config, check)

def testResReqConflictingDefs(databases):
    """Test what happens if resource requirements from the framework
    and task definitions disagree about a resource's type.
    While we don't allow changing an inherted resource type when editing
    a task definition, there can be a conflict if the type is changed
    in the framework definition later.
    """

    def check(config):
        job, = config.createJobs(OWNER)

        task = job.getTask('task')
        checkResourceClaim(specs, task.resourceClaim)

    gen = DataGenerator(databases)
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
    runWithReload(databases, config, check)

def testResReqAssignCombinedDefs(databases):
    """Test whether simple resource requirements from both the framework
    and task definition are used in task assignment."""

    def check(config):
        resourceDB = databases.resourceDB

        job, = config.createJobs(OWNER)
        taskRunner = resourceDB[tr]

        # Try to assign with both cap_a and cap_b unavailable.
        reserveResource(resourceDB, resA)
        reserveResource(resourceDB, resB)
        task = job.assignTask(taskRunner)
        assert task is None

        # Try to assign with only cap_a unavailable.
        freeResource(resourceDB, resB)
        task = job.assignTask(taskRunner)
        assert task is None

        # Try to assign with only cap_b unavailable.
        freeResource(resourceDB, resA)
        reserveResource(resourceDB, resB)
        task = job.assignTask(taskRunner)
        assert task is None

        # Try to assign with cap_a and cap_b available.
        freeResource(resourceDB, resB)
        task = job.assignTask(taskRunner)
        assert task is not None
        assert not resourceDB[resA].isFree()
        assert not resourceDB[resB].isFree()
        assert resourceDB[resC].isFree()
        job.taskDone('task', ResultCode.OK, 'summary text', (), {})
        assert resourceDB[resA].isFree()
        assert resourceDB[resB].isFree()
        assert resourceDB[resC].isFree()

    gen = DataGenerator(databases)
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
    runWithReload(databases, config, check)

def testResReqAssignNonExclusive(databases):
    """Test assigning task using a non-exclusive resource."""

    def check(config):
        job, = config.createJobs(OWNER)
        taskRunner = databases.resourceDB[tr]

        # Try to assign with resource unavailable.
        reserveResource(databases.resourceDB, res)
        task = job.assignTask(taskRunner)
        assert task is None

        # Try to assign with resource available.
        freeResource(databases.resourceDB, res)
        task = job.assignTask(taskRunner)
        assert task is not None
        assert databases.resourceDB[res].isFree()
        job.taskDone('task', ResultCode.OK, 'summary text', (), {})
        assert databases.resourceDB[res].isFree()

    gen = DataGenerator(databases)
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
    runWithReload(databases, config, check)

def testResReqTypeConflict(databases):
    """Test configuration using different types for same reference."""

    def checkConsistent(config):
        assert config.isConsistent(databases.resTypeDB)
    def checkInconsistent(config):
        assert not config.isConsistent(databases.resTypeDB)

    gen = DataGenerator(databases)
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
    runWithReload(databases, config, checkConsistent)
    # Update resource type A to be also per-job exclusive.
    databases.resTypeDB.update(ResType.create(resTypeA, True, True))
    runWithReload(databases, config, checkConsistent)
    # Update resource type B to be also per-job exclusive.
    databases.resTypeDB.update(ResType.create(resTypeB, True, True))
    runWithReload(databases, config, checkInconsistent)

def testResReqDoubleReserve(databases, caplog):
    """Test reserving the same resource twice."""

    gen = DataGenerator(databases)
    resType = gen.createResourceType()
    res = gen.createResource(resType)

    resourceDB = databases.resourceDB
    reserveResource(resourceDB, res)

    resource = resourceDB[res]
    resource.reserve('twice')
    logged, = caplog.records
    assert logged.levelname == 'ERROR'
    assert 'already reserved' in logged.message
    assert resource.isReserved()

def testResReqDoubleFree(databases, caplog):
    """Test freeing the same resource twice."""

    gen = DataGenerator(databases)
    resType = gen.createResourceType()
    res = gen.createResource(resType)

    resourceDB = databases.resourceDB
    reserveResource(resourceDB, res)
    freeResource(resourceDB, res)

    resource = resourceDB[res]
    resource.free()
    logged, = caplog.records
    assert logged.levelname == 'ERROR'
    assert 'not reserved' in logged.message
    assert not resource.isReserved()

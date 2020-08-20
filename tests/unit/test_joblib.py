# SPDX-License-Identifier: BSD-3-Clause

"""Test job functionality.

Every test case checks both the in-memory database (same db object on which
operations were performed) and the on-disk database (used to load data
after Databases.reload() call is performed).
"""

import random

from pytest import raises

from softfab.resultcode import ResultCode
from softfab.taskgroup import TaskGroup
from softfab.utils import IllegalStateError

from datageneratorlib import DataGenerator


def locatorForTask(taskId):
    return 'dummylocator@' + taskId

def taskDone(job, taskId, result=ResultCode.OK):
    """Marks a task as done, including all required locators."""

    locators = {}
    if result is not ResultCode.ERROR:
        for out in job.getTask(taskId).getOutputs():
            locators[out] = locatorForTask(taskId)
    job.taskDone(taskId, result, 'summary text', (), locators)

def runWithReload(databases, config, verifyFunc):
    configId = config.getId()
    verifyFunc(config)
    # TODO: Speed up job creation by adding to DB only after job is complete.
    #databases.configDB.add(config)
    databases.reload()
    config = databases.configDB[configId]
    verifyFunc(config)

def sanityCheck(gen, config):
    # Verify job inputs.
    ### Not valid for configs any more
    inputs = sorted(prod['name'] for prod in config.getInputs())
    gen.inputsCreated.sort()
    assert inputs == gen.inputsCreated

    # Verify task sequence.
    available = set(gen.inputsCreated)
    taskSequence = config.getTaskSequence()
    tasksLeft = set(gen.tasks)
    for task in taskSequence:
        taskId = task.getName()
        assert taskId in tasksLeft
        tasksLeft.remove(taskId)
        for inp in task.getInputs():
            assert inp in available
        for out in task.getOutputs():
            # Note: Currently, we do accept one output being produced
            #       multiple times, the first time counts and the other
            #       times are ignored. See test0041 for details.
            #assert out not in available
            available.add(out)
    assert tasksLeft == set()

def simulate(databases, gen, config, checkFunc=None):
    #print('simulate', config.getId())

    sanityCheck(gen, config)

    # TODO: Is it OK that Config.createJob does not put record into job DB?
    #       If so, document.
    job, = config.createJobs(gen.owner)
    # Note: Disabled to save time.
    # TODO: The toXML functionality should probably be tested
    #       in a separate test case.
    #databases.jobDB.add(job)

    # Verify execution.
    rnd = gen.rnd
    available = set(gen.inputsCreated)
    tasksLeft = set(gen.tasks)
    # TODO: Do not use a list (performance).
    freeTaskRunners = list(gen.taskRunners)
    rnd.shuffle(freeTaskRunners)
    usedTaskRunners = []
    while True:
        newFreeTaskRunners = []
        for taskRunner in freeTaskRunners:
            trRecord = databases.resourceDB[taskRunner]
            taskRun = job.assignTask(trRecord)
            if taskRun is None:
                newFreeTaskRunners.append(taskRunner)
            else:
                task = taskRun.getTask()
                # Verify capabilities.
                trCaps = trRecord.capabilities
                for cap in task.getNeededCaps():
                    assert cap in trCaps
                # Update administration.
                taskName = task.getName()
                usedTaskRunners.append((taskRunner, taskName))
                assert taskName in tasksLeft
                tasksLeft.remove(taskName)
                for inp in task.getInputs():
                    assert inp in available
                    # Check whether the right Task Runner is used
                    # for local products.
                    inpProd = job.getProduct(inp)
                    if inpProd.isLocal():
                        assert inpProd.getLocalAt() == taskRunner
                for out in task.getOutputs():
                    # Note: Currently, we do accept one output being
                    #       produced multiple times, the first time counts
                    #       and the other times are ignored.
                    #       See test0041 for details.
                    #assert out not in available
                    available.add(out)
        freeTaskRunners = newFreeTaskRunners
        if usedTaskRunners == []:
            # All Task Runners are free and still unable to assign.
            break
        # Pick a Task Runner and let it finish its task.
        index = rnd.randrange(len(usedTaskRunners))
        taskRunner, taskId = usedTaskRunners[index]
        del usedTaskRunners[index]
        freeTaskRunners.append(taskRunner)
        rnd.shuffle(freeTaskRunners)
        taskDone(job, taskId)
    if checkFunc is not None:
        checkFunc(gen, job)
    else:
        assert tasksLeft == set()

def randomRuns(databases, runs, rnd, genClass, checkFunc=None):
    for run in range(runs):
        gen = genClass(databases, rnd, run)
        gen.createDefinitions()
        gen.createTaskRunners()
        config = gen.createConfiguration()
        gen.addCapabilities(config)
        gen.setInputs(config)
        # TODO: Write a separate log file for stats such as these.
        #print('number of products:', len(gen.products))
        #print('number of inputs:', len(gen.inputsCreated))
        #print('number of input groups:', len(config.getInputsGrouped()))
        runWithReload(databases, config,
            lambda config: simulate(databases, gen, config, checkFunc)
            )

def testJobProperties(databases):
    """Test whether global job properties are preserved."""

    def checkProperties(config):
        jobId = 'job0'
        assert config.targets == {'target1', 'target2'}
        assert config.getId() == jobId
        assert config['name'] == jobId
        assert config.owner == gen.owner
        assert config['owner'] == gen.owner
        assert config.comment == gen.comment
        #assert config.getDescription() == config['description']

    gen = DataGenerator(databases)
    config = gen.createConfiguration(
        targets=('target1', 'target2')
        )
    runWithReload(databases, config, checkProperties)

def testJobEmpty(databases):
    """Test whether empty job behaves correctly."""

    def checkEmpty(config):
        assert config.getParameter('') == None
        assert len(config.getInputs()) == 0
        assert len(config.getInputsGrouped()) == 0
        assert len(config.getTasks()) == 0
        assert len(config.getTaskSequence()) == 0

    config = DataGenerator(databases).createConfiguration()
    runWithReload(databases, config, checkEmpty)

def testJobOneTask(databases):
    """Test job with 1 task in it."""

    class CustomGenerator(DataGenerator):
        numTasks = 1
        numInputs = [ 0 ]
        numOutputs = [ 0 ]

    gen = CustomGenerator(databases)
    gen.createDefinitions()
    config = gen.createConfiguration()

    def checkOne(config):
        taskName = gen.tasks[0]
        #assert config.getProduct('') is None
        assert len(config.getInputs()) == 0
        assert len(config.getInputsGrouped()) == 0
        assert len(config.getTasks()) == 1
        task, = config.getTasks()
        assert task is not None
        assert task.getName() == taskName
        assert len(config.getTaskSequence()) == 1

    runWithReload(databases, config, checkOne)

def testJobDependencies(databases):
    """Test dependency resolution."""

    class CustomGenerator(DataGenerator):
        pass

    seed = 0
    rnd = random.Random(seed)
    runs = 10
    randomRuns(databases, runs, rnd, CustomGenerator)

def testJobTwiceProduct(databases):
    """Test producing the same product twice.
    This reproduces a problem that occurred in the LVS SoftFab on 2005-06-21.
    """

    class CustomGenerator(DataGenerator):
        pass
    gen = CustomGenerator(databases)

    image = gen.createProduct('image')
    buildFw = gen.createFramework('build', [], [ image ])
    testFw = gen.createFramework('test', [ image ], [])
    buildTask1 = gen.createTask('build1', buildFw)
    buildTask2 = gen.createTask('build2', buildFw)
    testTask = gen.createTask('test', testFw)

    buildTR = gen.createTaskRunner(name='tr_build', capabilities=['build'])
    testTR = gen.createTaskRunner(name='tr_test', capabilities=['test'])

    def simulate(config):
        sanityCheck(gen, config)

        # TODO: Is it OK that Config.createJob does not put record into
        #       job DB? If so, document.
        job, = config.createJobs(gen.owner)
        # Note: Disabled to save time.
        # TODO: The toXML functionality should probably be tested
        #       in a separate test case.
        #self.jobDB.add(job)

        # Verify execution:
        # Successfully complete first build task.
        task = job.assignTask(databases.resourceDB[buildTR])
        assert task is not None
        assert task.getName().startswith('build')
        taskDone(job, task.getName())
        # Start test task.
        task = job.assignTask(databases.resourceDB[testTR])
        assert task is not None
        assert task.getName() == testTask
        # Complete second build task, but make it fail.
        task = job.assignTask(databases.resourceDB[buildTR])
        assert task is not None
        assert task.getName().startswith('build')
        taskDone(job, task.getName(), ResultCode.ERROR)
        # Successfully complete test task.
        taskDone(job, testTask)
        assert job.isExecutionFinished()
        assert job.hasFinalResult()

    runWithReload(databases, gen.createConfiguration(), simulate)

def testJobMultiTaskRunner(databases):
    """Test execution using multiple Task Runners."""

    class CustomGenerator(DataGenerator):
        chanceChainProduct = 0.4
        numTaskRunners = 5
        chanceTRFramework = 0.7

        def frameworksForTaskRunner(self):
            return [
                framework for framework in self.frameworks
                if self.rnd.random() < self.chanceTRFramework
                ]

    seed = 123456789
    rnd = random.Random(seed)
    runs = 10
    randomRuns(databases, runs, rnd, CustomGenerator)

def testJobTRSetRestrictJob(databases):
    """Test Task Runner restrictions at the job level.
    Two Task Runners, only one is allowed at the job level.
    """
    gen = DataGenerator(databases)
    fwName = gen.createFramework('testfw1')
    taskName = gen.createTask('task1', fwName)
    tr1Name = gen.createTaskRunner(capabilities=[fwName])
    tr2Name = gen.createTaskRunner(capabilities=[fwName])
    config = gen.createConfiguration()
    config._setRunners([tr2Name])
    config._notify()
    def simulate(config):
        sanityCheck(gen, config)
        job, = config.createJobs(gen.owner)
        task = job.assignTask(databases.resourceDB[tr1Name])
        assert task is None
        assert not job.isExecutionFinished()
        assert not job.hasFinalResult()
        task = job.assignTask(databases.resourceDB[tr2Name])
        assert task is not None
        taskDone(job, task.getName())
        assert job.isExecutionFinished()
        assert job.hasFinalResult()
    runWithReload(databases, config, simulate)

def testJobTRSetRestrictTask(databases):
    """Test Task Runner restrictions at the task level.
    Two Task Runners, only one is allowed at the task level.
    """
    gen = DataGenerator(databases)
    fwName = gen.createFramework('testfw1')
    taskName = gen.createTask('task1', fwName)
    tr1Name = gen.createTaskRunner(capabilities=[fwName])
    tr2Name = gen.createTaskRunner(capabilities=[fwName])
    config = gen.createConfiguration()
    config.getTask(taskName)._setRunners([tr2Name])
    config._notify()
    def simulate(config):
        sanityCheck(gen, config)
        job, = config.createJobs(gen.owner)
        task = job.assignTask(databases.resourceDB[tr1Name])
        assert task is None
        assert not job.isExecutionFinished()
        assert not job.hasFinalResult()
        task = job.assignTask(databases.resourceDB[tr2Name])
        assert task is not None
        taskDone(job, task.getName())
        assert job.isExecutionFinished()
        assert job.hasFinalResult()
    runWithReload(databases, config, simulate)

def testJobTRSetOverride(databases):
    """Test overriding Task Runner restrictions.
    Two Task Runners, one allowed at the job level
    and overridden at the task level.
    """
    gen = DataGenerator(databases)
    fwName = gen.createFramework('testfw1')
    taskName = gen.createTask('task1', fwName)
    tr1Name = gen.createTaskRunner(capabilities=[fwName])
    tr2Name = gen.createTaskRunner(capabilities=[fwName])
    config = gen.createConfiguration()
    config._setRunners([tr1Name])
    config.getTask(taskName)._setRunners([tr2Name])
    config._notify()
    def simulate(config):
        sanityCheck(gen, config)
        job, = config.createJobs(gen.owner)
        task = job.assignTask(databases.resourceDB[tr1Name])
        assert task is None
        assert not job.isExecutionFinished()
        assert not job.hasFinalResult()
        task = job.assignTask(databases.resourceDB[tr2Name])
        assert task is not None
        taskDone(job, task.getName())
        assert job.isExecutionFinished()
        assert job.hasFinalResult()
    runWithReload(databases, config, simulate)

def testJobTRSetNoCaps(databases):
    """Test that Task Runner restrictions do not override capabilities.
    One Task Runner, explicitly allowed both at the task
    and at the job level, but does not have required capability.
    """
    gen = DataGenerator(databases)
    fwName = gen.createFramework('testfw1')
    taskName = gen.createTask('task1', fwName)
    tr1Name = gen.createTaskRunner(capabilities=['dummy'])
    config = gen.createConfiguration()
    config._setRunners([tr1Name])
    config.getTask(taskName)._setRunners([tr1Name])
    config._notify()
    def simulate(config):
        sanityCheck(gen, config)
        job, = config.createJobs(gen.owner)
        task = job.assignTask(databases.resourceDB[tr1Name])
        assert task is None
        assert not job.isExecutionFinished()
        assert not job.hasFinalResult()
    runWithReload(databases, config, simulate)

def testJobTRSetLocalInput(databases):
    """Test that Task Runner restrictions do not override local inputs.
    Two Task Runners, one is allowed at the task level,
    local input is bound to the other task runner.
    """
    gen = DataGenerator(databases)
    prodName = gen.createProduct('input1', True)
    fwName = gen.createFramework('testfw1', [prodName])
    taskName = gen.createTask('task1', fwName)
    tr1Name = gen.createTaskRunner(capabilities=[fwName])
    tr2Name = gen.createTaskRunner(capabilities=[fwName])
    config = gen.createConfiguration()
    config._addInput({
        'name': prodName,
        'locator': 'dummy',
        'localAt': tr2Name
        })
    config.getTask(taskName)._setRunners([tr1Name])
    config._notify()
    # TODO: This is a hack to prevent 'sanityCheck' from reporting an error
    gen.inputsCreated = [prodName]
    def simulate(config):
        sanityCheck(gen, config)
        job, = config.createJobs(gen.owner)
        task = job.assignTask(databases.resourceDB[tr1Name])
        assert task is None
        assert not job.isExecutionFinished()
        assert not job.hasFinalResult()
    runWithReload(databases, config, simulate)

def testJobTRSetRandomRun(databases):
    """Random runs with task runner restrictions."""

    class CustomGenerator(DataGenerator):
        chanceChainProduct = 0.4
        numTaskRunners = 5
        chanceTRFramework = 0.7
        chanceTRAllowedForJob = 0.7
        chanceTRAllowedForTask = 0.5
        chanceTRSetOverride = 0.4

        def frameworksForTaskRunner(self):
            return [
                framework for framework in self.frameworks
                if self.rnd.random() < self.chanceTRFramework
                ]

        def createConfiguration(self):
            def randomTRSet(chance):
                return (
                    tr for tr in self.taskRunners
                    if self.rnd.random() < chance
                    )
            config = DataGenerator.createConfiguration(self)
            config._setRunners(randomTRSet(self.chanceTRAllowedForJob))
            for task in config.getTasks():
                if self.rnd.random() < self.chanceTRSetOverride:
                    task._setRunners(
                        randomTRSet(self.chanceTRAllowedForTask)
                        )
            config._notify()
            return config

    def checkResults(gen, job):

        def checkExecutionFinishedTask(task):
            assert task.isDone()
            taskRunners = task.getRunners() or job.getRunners()
            runnerId = task['runner']
            if taskRunners:
                assert runnerId in taskRunners
            trCaps = databases.resourceDB[runnerId].capabilities
            for cap in task.getNeededCaps():
                assert cap in trCaps

        def allInputsReady(task):
            for input in task.getInputs():
                if not job.getProduct(input).isAvailable():
                    return False
            return True

        def checkTaskRunners(task, onlyThis = None):
            if onlyThis is not None:
                taskRunners = [onlyThis]
            else:
                taskRunners = task.getRunners() or job.getRunners()
            for runnerId in taskRunners:
                # Target is not checked here, because DataGenerator uses
                # the same target for the job and all the task runners.
                assert not databases.resourceDB[runnerId].capabilities \
                        >= task.getNeededCaps()

        def checkNotDone(tasksNotDone, noTasksDone, runnerId):
            #assert noTasksDone
            if runnerId is None:
                assert noTasksDone
            else:
                assert len(tasksNotDone) != 0
                for task in tasksNotDone:
                    if allInputsReady(task):
                        assert runnerId not in \
                            (task.getRunners() or job.getRunners())

        for item in job.getTaskGroupSequence():
            if isinstance(item, TaskGroup):
                runnerId = item.getRunnerId()
                neededCaps = item.getNeededCaps()
                noTasksDone = True
                tasksNotDone = []
                taskRunners = None
                for task in item.getChildren():
                    runners = task.getRunners() or job.getRunners()
                    if runners:
                        if taskRunners is None:
                            taskRunners = set(runners)
                        else:
                            taskRunners &= runners
                    if task.isExecutionFinished():
                        checkExecutionFinishedTask(task)
                        assert task['runner'] == runnerId
                        noTasksDone = False
                    else:
                        tasksNotDone.append(task)
                if taskRunners is None:
                    assert len(tasksNotDone) == 0
                elif taskRunners:
                    if runnerId in taskRunners:
                        for task in tasksNotDone:
                            if allInputsReady(task):
                                checkTaskRunners(task, runnerId)
                    else:
                        checkNotDone(tasksNotDone, noTasksDone, runnerId)
                else:
                    checkNotDone(tasksNotDone, noTasksDone, runnerId)
            else:
                task = item # item is a task
                if task.isExecutionFinished():
                    checkExecutionFinishedTask(task)
                elif allInputsReady(task):
                    checkTaskRunners(task)

    seed = 123456789
    rnd = random.Random(seed)
    runs = 10
    randomRuns(databases, runs, rnd, CustomGenerator, checkResults)

def testJobCombinedProduct(databases):
    """Verifies that a combined product becomes available after all tasks
    that can produce it have run, whether those tasks end in "ok" or
    "error".
    """

    class CustomGenerator(DataGenerator):
        pass
    gen = CustomGenerator(databases)

    image = gen.createProduct('image', False, True)
    buildFw = gen.createFramework('build', [], [ image ])
    testFw = gen.createFramework('test', [ image ], [])
    buildTask1 = gen.createTask('build1', buildFw)
    buildTask2 = gen.createTask('build2', buildFw)
    testTask = gen.createTask('test', testFw)

    buildTR = gen.createTaskRunner(name='tr_build', capabilities=['build'])
    testTR = gen.createTaskRunner(name='tr_test', capabilities=['test'])

    def simulate(config):
        sanityCheck(gen, config)

        job, = config.createJobs(gen.owner)
        # TODO: The toXML functionality should probably be tested
        #       in a separate test case.

        # Verify execution:
        # Successfully complete first build task.
        task = job.assignTask(databases.resourceDB[buildTR])
        assert task is not None
        assert task.getName().startswith('build')
        taskDone(job, task.getName())
        # Try to start test task (should fail).
        task = job.assignTask(databases.resourceDB[testTR])
        assert task is None
        # Complete second build task, but make it fail.
        task = job.assignTask(databases.resourceDB[buildTR])
        assert task is not None
        assert task.getName().startswith('build')
        taskDone(job, task.getName(), ResultCode.ERROR)
        # Try to start test task (should succeed).
        task = job.assignTask(databases.resourceDB[testTR])
        assert task is not None
        assert task.getName() == testTask
        # Successfully complete test task.
        taskDone(job, testTask)
        assert job.isExecutionFinished()
        assert job.hasFinalResult()
        # Check that locators have been stored separately.
        producers = set()
        for taskId, locator in job.getProduct(image).getProducers():
            assert taskId.startswith('build')
            assert locator == locatorForTask(taskId)

    runWithReload(databases, gen.createConfiguration(), simulate)

def testJobPostponedInspection(databases):
    """Tests job execution where the results are not known at the time that
    the execution finishes.
    """

    class CustomGenerator(DataGenerator):
        pass
    gen = CustomGenerator(databases)

    image = gen.createProduct('image')
    buildFw = gen.createFramework('build', [], [ image ])
    testFw = gen.createFramework('test', [ image ], [])
    buildTask = gen.createTask('build', buildFw)
    testTask1 = gen.createTask('test1', testFw)
    testTask2 = gen.createTask('test2', testFw)
    testTask3 = gen.createTask('test3', testFw)

    tr = gen.createTaskRunner(name='tr_build',
                                capabilities=['build', 'test'])

    def simulate(config):
        sanityCheck(gen, config)

        job, = config.createJobs(gen.owner)
        # TODO: The toXML functionality should probably be tested
        #       in a separate test case.

        # Verify execution:
        # Successfully complete first build task.
        task = job.assignTask(databases.resourceDB[tr])
        assert task is not None
        assert task.getName() == buildTask
        taskDone(job, buildTask)
        assert job.result == ResultCode.OK
        assert job.getFinalResult() == None
        # Successfully complete first test task, without result.
        task = job.assignTask(databases.resourceDB[tr])
        assert (task is not None) is not None
        assert task.getName() == testTask1
        taskDone(job, testTask1, ResultCode.INSPECT)
        assert not job.isExecutionFinished()
        assert not job.hasFinalResult()
        assert job.result == ResultCode.INSPECT
        assert job.getFinalResult() is None
        # Successfully complete second test task, with result.
        task = job.assignTask(databases.resourceDB[tr])
        assert task is not None
        assert task.getName() == testTask2
        taskDone(job, testTask2, ResultCode.OK)
        assert not job.isExecutionFinished()
        assert not job.hasFinalResult()
        assert job.result == ResultCode.INSPECT
        assert job.getFinalResult() is None
        # Successfully complete third test task, without result.
        task = job.assignTask(databases.resourceDB[tr])
        assert task is not None
        assert task.getName() == testTask3
        taskDone(job, testTask3, ResultCode.INSPECT)
        assert job.isExecutionFinished()
        assert not job.hasFinalResult()
        assert job.result == ResultCode.INSPECT
        assert job.getFinalResult() is None
        # Attempt to set invalid inspection result.
        with raises(ValueError):
            job.inspectDone(testTask1, ResultCode.CANCELLED, 'invalid')
        # Complete inspection of first task.
        job.inspectDone(testTask1, ResultCode.WARNING, 'inspect 1')
        assert job.isExecutionFinished()
        assert not job.hasFinalResult()
        assert job.result == ResultCode.INSPECT
        assert job.getFinalResult() is None
        # Attempt to change inspection result.
        with raises(IllegalStateError):
            job.inspectDone(testTask1, ResultCode.OK, 'invalid')
        # Complete inspection of third task.
        job.inspectDone(testTask3, ResultCode.OK, 'inspect 3')
        assert job.isExecutionFinished()
        assert job.hasFinalResult()
        assert job.result == ResultCode.WARNING
        assert job.getFinalResult() == ResultCode.WARNING

    runWithReload(databases, gen.createConfiguration(), simulate)

def testJobTRLostWhileRunning(databases):
    """Test what happens when a busy Task Runner is lost."""
    gen = DataGenerator(databases)
    fwName = gen.createFramework('testfw1')
    taskName = gen.createTask('task1', fwName)
    trName = gen.createTaskRunner(capabilities=[fwName])
    config = gen.createConfiguration()

    sanityCheck(gen, config)
    job, = config.createJobs(gen.owner)
    runner = databases.resourceDB[trName]
    task = job.assignTask(runner)
    assert task is not None
    assert task.isRunning()
    runner.markLost()
    assert not task.isRunning()
    assert task.result == ResultCode.ERROR

def testJobTRRemovedWhileRunning(databases):
    """Test what happens when a busy Task Runner is removed."""
    gen = DataGenerator(databases)
    fwName = gen.createFramework('testfw1')
    taskName = gen.createTask('task1', fwName)
    trName = gen.createTaskRunner(capabilities=[fwName])
    config = gen.createConfiguration()

    sanityCheck(gen, config)
    job, = config.createJobs(gen.owner)
    runner = databases.resourceDB[trName]
    task = job.assignTask(runner)
    assert task is not None
    assert task.isRunning()
    databases.resourceDB.remove(runner)
    assert not task.isRunning()
    assert task.result == ResultCode.ERROR

def testJobResourceRemovedWhileRunning(databases):
    """Test what happens when a non-TR resource removed while in use.
    Unlike with a TR, this is not a reason to fail the task, since it
    may be possible for the task to complete successfully.
    For example, removal of the resource may simply be the resource
    management being moved outside of SoftFab.
    """
    gen = DataGenerator(databases)
    resType = gen.createResourceType(pertask=True)
    fwName = gen.createFramework(
        name='testfw1',
        resources= [('ref1', resType, ())]
        )
    taskName = gen.createTask('task1', fwName)
    trName = gen.createTaskRunner(capabilities=[fwName])
    config = gen.createConfiguration()
    resName = gen.createResource(resType)

    sanityCheck(gen, config)
    job, = config.createJobs(gen.owner)
    runner = databases.resourceDB[trName]
    resource = databases.resourceDB[resName]
    task = job.assignTask(runner)
    assert task is not None
    assert task.isRunning()
    assert resource.isReserved()
    databases.resourceDB.remove(resource)
    assert task.isRunning()
    assert task.result is None
    taskDone(job, taskName, ResultCode.OK)
    assert job.isExecutionFinished()
    assert job.hasFinalResult()
    assert job.result == ResultCode.OK
    assert job.getFinalResult() == ResultCode.OK

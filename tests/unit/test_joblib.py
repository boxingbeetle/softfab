# SPDX-License-Identifier: BSD-3-Clause

import random, unittest

from initconfig import config

from softfab import databases
from softfab import configlib, resourcelib, taskgroup
from softfab.resultcode import ResultCode
from softfab.timelib import setTime
from softfab.utils import IllegalStateError

from datageneratorlib import removeRec, DataGenerator

def locatorForTask(taskId):
    return 'dummylocator@' + taskId

def taskDone(job, taskId, result = ResultCode.OK):
    """Marks a task as done, including all required locators.
    """
    locators = {}
    if result is not ResultCode.ERROR:
        for out in job.getTask(taskId).getOutputs():
            locators[out] = locatorForTask(taskId)
    job.taskDone(taskId, result, 'summary text', locators)

class TestJobs(unittest.TestCase):
    """Test job functionality.

    Every test case checks both the in-memory database (same db object on which
    operations were performed) and the on-disk database (used to load data
    after reloadDatabases() call is performed).
    """

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)
        self.target = 'target1'
        self.owner = 'owner1'
        self.comment = 'this is a comment'
        self.jobId = 'job1'

        # Stop time, so Task Runner will not get out of sync.
        setTime(1000)

    def setUp(self):
        self.reloadDatabases()

    def tearDown(self):
        removeRec(config.dbDir)

    def reloadDatabases(self):
        databases.reloadDatabases()

    def runWithReload(self, config, verifyFunc):
        configId = config.getId()
        verifyFunc(config)
        # TODO: Speed up job creation by adding to DB only after job is complete.
        #configlib.db.add(config)
        self.reloadDatabases()
        config = configlib.configDB[configId]
        verifyFunc(config)

    def randomRuns(self, runs, rnd, genClass, checkFunc = None):
        for run in range(runs):
            gen = genClass(rnd, run)
            gen.createDefinitions()
            gen.createTaskRunners()
            config = gen.createConfiguration()
            gen.addCapabilities(config)
            gen.setInputs(config)
            # TODO: Write a separate log file for stats such as these.
            #print 'number of products:', len(gen.products)
            #print 'number of inputs:', len(gen.inputsCreated)
            #print 'number of input groups:', len(config.getInputsGrouped())
            self.runWithReload(config,
                lambda config: self.simulate(gen, config, checkFunc)
                )

    def sanityCheck(self, gen, config):
        # Verify job inputs.
        ### Not valid for configs any more
        inputs = [ prod['name'] for prod in config.getInputs() ]
        inputs.sort()
        gen.inputsCreated.sort()
        self.assertEqual(inputs, gen.inputsCreated)

        # Verify task sequence.
        available = set(gen.inputsCreated)
        taskSequence = config.getTaskSequence()
        tasksLeft = set(gen.tasks)
        for task in taskSequence:
            taskId = task.getName()
            self.assertIn(taskId, tasksLeft)
            tasksLeft.remove(taskId)
            for inp in task.getInputs():
                self.assertIn(inp, available)
            for out in task.getOutputs():
                # Note: Currently, we do accept one output being produced
                #       multiple times, the first time counts and the other
                #       times are ignored. See test0041 for details.
                #self.assert_(out not in available)
                available.add(out)
        self.assertEqual(tasksLeft, set())

    def simulate(self, gen, config, checkFunc = None):
        #print 'simulate', config.getId()

        self.sanityCheck(gen, config)

        # TODO: Is it OK that Config.createJob does not put record into job DB?
        #       If so, document.
        job = config.createJob(self.owner)
        # Note: Disabled to save time.
        # TODO: The toXML functionality should probably be tested
        #       in a separate test case.
        #joblib.jobDB.add(job)

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
                trRecord = resourcelib.taskRunnerDB[taskRunner]
                taskRun = job.assignTask(trRecord)
                if taskRun is None:
                    newFreeTaskRunners.append(taskRunner)
                else:
                    task = taskRun.getTask()
                    # Verify capabilities.
                    trCaps = trRecord.capabilities
                    for cap in task.getNeededCaps():
                        self.assertIn(cap, trCaps)
                    # Update administration.
                    taskName = task.getName()
                    usedTaskRunners.append( (taskRunner, taskName) )
                    self.assertIn(taskName, tasksLeft)
                    tasksLeft.remove(taskName)
                    for inp in task.getInputs():
                        self.assertIn(inp, available)
                        # Check whether the right Task Runner is used
                        # for local products.
                        inpProd = job.getProduct(inp)
                        if inpProd.isLocal():
                            self.assertEqual(inpProd.getLocalAt(), taskRunner)
                    for out in task.getOutputs():
                        # Note: Currently, we do accept one output being
                        #       produced multiple times, the first time counts
                        #       and the other times are ignored.
                        #       See test0041 for details.
                        #self.assert_(out not in available)
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
            self.assertEqual(tasksLeft, set())

    def test0010Properties(self):
        "Test whether global job properties are preserved."

        def checkProperties(config):
            jobId = 'job0'
            self.assertEqual(config['target'], self.target)
            self.assertEqual(config.getId(), jobId)
            self.assertEqual(config['name'], jobId)
            self.assertEqual(config.getOwner(), self.owner)
            self.assertEqual(config['owner'], self.owner)
            self.assertEqual(config.comment, self.comment)
            #self.assertEqual(config.getDescription(), config['description'])

        config = DataGenerator().createConfiguration()
        self.runWithReload(config, checkProperties)

    def test0020Empty(self):
        "Test whether empty job behaves correctly."

        def checkEmpty(config):
            self.assertEqual(config.getParameter(''), None)
            self.assertEqual(len(config.getInputs()), 0)
            self.assertEqual(len(config.getInputsGrouped()), 0)
            self.assertEqual(len(config.getTasks()), 0)
            self.assertEqual(len(config.getTaskSequence()), 0)

        config = DataGenerator().createConfiguration()
        self.runWithReload(config, checkEmpty)

    def test0030One(self):
        "Test job with 1 task in it."

        class CustomGenerator(DataGenerator):
            numTasks = 1
            numInputs = [ 0 ]
            numOutputs = [ 0 ]

        gen = CustomGenerator()
        gen.createDefinitions()
        config = gen.createConfiguration()

        def checkOne(config):
            taskName = gen.tasks[0]
            #self.assertEqual(config.getProduct(''), None)
            self.assertEqual(len(config.getInputs()), 0)
            self.assertEqual(len(config.getInputsGrouped()), 0)
            self.assertEqual(len(config.getTasks()), 1)
            task, = config.getTasks()
            self.assertIsNotNone(task)
            self.assertEqual(task.getName(), taskName)
            self.assertEqual(len(config.getTaskSequence()), 1)

        self.runWithReload(config, checkOne)

    def test0040Dependencies(self):
        "Test dependency resolution."

        class CustomGenerator(DataGenerator):
            pass

        seed = 0
        rnd = random.Random(seed)
        runs = 10
        self.randomRuns(runs, rnd, CustomGenerator)

    def test0041TwiceProduct(self):
        """Test producing the same product twice.
        This reproduces a problem that occurred in the LVS SoftFab
        on 2005-06-21.
        """

        class CustomGenerator(DataGenerator):
            pass
        gen = CustomGenerator()

        image = gen.createProduct('image')
        buildFw = gen.createFramework('build', [], [ image ])
        testFw = gen.createFramework('test', [ image ], [])
        buildTask1 = gen.createTask('build1', buildFw)
        buildTask2 = gen.createTask('build2', buildFw)
        testTask = gen.createTask('test', testFw)

        buildTR = gen.createTaskRunner('tr_build', gen.target, [ 'build' ])
        testTR = gen.createTaskRunner('tr_test', gen.target, [ 'test' ])

        def simulate(config):
            self.sanityCheck(gen, config)

            # TODO: Is it OK that Config.createJob does not put record into
            #       job DB? If so, document.
            job = config.createJob(self.owner)
            # Note: Disabled to save time.
            # TODO: The toXML functionality should probably be tested
            #       in a separate test case.
            #joblib.jobDB.add(job)

            # Verify execution:
            # Successfully complete first build task.
            task = job.assignTask(resourcelib.taskRunnerDB[buildTR])
            self.assertIsNotNone(task)
            self.assertTrue(task.getName().startswith('build'))
            taskDone(job, task.getName())
            # Start test task.
            task = job.assignTask(resourcelib.taskRunnerDB[testTR])
            self.assertIsNotNone(task)
            self.assertEqual(task.getName(), testTask)
            # Complete second build task, but make it fail.
            task = job.assignTask(resourcelib.taskRunnerDB[buildTR])
            self.assertIsNotNone(task)
            self.assertTrue(task.getName().startswith('build'))
            taskDone(job, task.getName(), ResultCode.ERROR)
            # Successfully complete test task.
            taskDone(job, testTask)
            self.assertTrue(job.isExecutionFinished())
            self.assertTrue(job.hasFinalResult())

        self.runWithReload(gen.createConfiguration(), simulate)

    def test0050MultiTaskRunner(self):
        "Test execution using multiple Task Runners."

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
        self.randomRuns(runs, rnd, CustomGenerator)

    def test0060TRSetRestrictJob(self):
        """Test Task Runner restrictions at the job level.
        Two Task Runners, only one is allowed at the job level.
        """
        gen = DataGenerator()
        fwName = gen.createFramework('testfw1')
        taskName = gen.createTask('task1', fwName)
        tr1Name = gen.createTaskRunner('tr1', gen.target, [fwName])
        tr2Name = gen.createTaskRunner('tr2', gen.target, [fwName])
        config = gen.createConfiguration()
        config._setRunners([tr2Name])
        config._notify()
        def simulate(config):
            self.sanityCheck(gen, config)
            job = config.createJob(self.owner)
            task = job.assignTask(resourcelib.taskRunnerDB[tr1Name])
            self.assertIsNone(task)
            self.assertFalse(job.isExecutionFinished())
            self.assertFalse(job.hasFinalResult())
            task = job.assignTask(resourcelib.taskRunnerDB[tr2Name])
            self.assertIsNotNone(task)
            taskDone(job, task.getName())
            self.assertTrue(job.isExecutionFinished())
            self.assertTrue(job.hasFinalResult())
        self.runWithReload(config, simulate)

    def test0070TRSetRestrictTask(self):
        """Test Task Runner restrictions at the task level.
        Two Task Runners, only one is allowed at the task level.
        """
        gen = DataGenerator()
        fwName = gen.createFramework('testfw1')
        taskName = gen.createTask('task1', fwName)
        tr1Name = gen.createTaskRunner('tr1', gen.target, [fwName])
        tr2Name = gen.createTaskRunner('tr2', gen.target, [fwName])
        config = gen.createConfiguration()
        config.getTask(taskName)._setRunners([tr2Name])
        config._notify()
        def simulate(config):
            self.sanityCheck(gen, config)
            job = config.createJob(self.owner)
            task = job.assignTask(resourcelib.taskRunnerDB[tr1Name])
            self.assertIsNone(task)
            self.assertFalse(job.isExecutionFinished())
            self.assertFalse(job.hasFinalResult())
            task = job.assignTask(resourcelib.taskRunnerDB[tr2Name])
            self.assertIsNotNone(task)
            taskDone(job, task.getName())
            self.assertTrue(job.isExecutionFinished())
            self.assertTrue(job.hasFinalResult())
        self.runWithReload(config, simulate)

    def test0080TRSetOverride(self):
        """Test overriding Task Runner restrictions.
        Two Task Runners, one allowed at the job level
        and overridden at the task level.
        """
        gen = DataGenerator()
        fwName = gen.createFramework('testfw1')
        taskName = gen.createTask('task1', fwName)
        tr1Name = gen.createTaskRunner('tr1', gen.target, [fwName])
        tr2Name = gen.createTaskRunner('tr2', gen.target, [fwName])
        config = gen.createConfiguration()
        config._setRunners([tr1Name])
        config.getTask(taskName)._setRunners([tr2Name])
        config._notify()
        def simulate(config):
            self.sanityCheck(gen, config)
            job = config.createJob(self.owner)
            task = job.assignTask(resourcelib.taskRunnerDB[tr1Name])
            self.assertIsNone(task)
            self.assertFalse(job.isExecutionFinished())
            self.assertFalse(job.hasFinalResult())
            task = job.assignTask(resourcelib.taskRunnerDB[tr2Name])
            self.assertIsNotNone(task)
            taskDone(job, task.getName())
            self.assertTrue(job.isExecutionFinished())
            self.assertTrue(job.hasFinalResult())
        self.runWithReload(config, simulate)

    def test0090TRSetNoCaps(self):
        """Test that Task Runner restrictions do not override capabilities.
        One Task Runner, explicitly allowed both at the task
        and at the job level, but does not have required capability.
        """
        gen = DataGenerator()
        fwName = gen.createFramework('testfw1')
        taskName = gen.createTask('task1', fwName)
        tr1Name = gen.createTaskRunner('tr1', gen.target, ['dummy'])
        config = gen.createConfiguration()
        config._setRunners([tr1Name])
        config.getTask(taskName)._setRunners([tr1Name])
        config._notify()
        def simulate(config):
            self.sanityCheck(gen, config)
            job = config.createJob(self.owner)
            task = job.assignTask(resourcelib.taskRunnerDB[tr1Name])
            self.assertIsNone(task)
            self.assertFalse(job.isExecutionFinished())
            self.assertFalse(job.hasFinalResult())
        self.runWithReload(config, simulate)

    def test0100TRSetLocalInput(self):
        """Test that Task Runner restrictions do not override local inputs.
        Two Task Runners, one is allowed at the task level,
        local input is bound to the other task runner.
        """
        gen = DataGenerator()
        prodName = gen.createProduct('input1', True)
        fwName = gen.createFramework('testfw1', [prodName])
        taskName = gen.createTask('task1', fwName)
        tr1Name = gen.createTaskRunner('tr1', gen.target, [fwName])
        tr2Name = gen.createTaskRunner('tr2', gen.target, [fwName])
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
            self.sanityCheck(gen, config)
            job = config.createJob(self.owner)
            task = job.assignTask(resourcelib.taskRunnerDB[tr1Name])
            self.assertIsNone(task)
            self.assertFalse(job.isExecutionFinished())
            self.assertFalse(job.hasFinalResult())
        self.runWithReload(config, simulate)

    def test0110TRSetRandomRun(self):
        "Random runs with task runner restrictions."

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
                self.assertTrue(task.isDone())
                taskRunners = task.getRunners() or job.getRunners()
                runnerId = task['runner']
                if taskRunners:
                    self.assertIn(runnerId, taskRunners)
                trCaps = resourcelib.taskRunnerDB[runnerId].capabilities
                for cap in task.getNeededCaps():
                    self.assertIn(cap, trCaps)

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
                    self.assertTrue(
                        not resourcelib.taskRunnerDB[runnerId].capabilities
                            >= task.getNeededCaps()
                        )

            def checkNotDone(tasksNotDone, noTasksDone, runnerId):
                #self.assert_(noTasksDone)
                if runnerId is None:
                    self.assertTrue(noTasksDone)
                else:
                    self.assertNotEqual(len(tasksNotDone), 0)
                    for task in tasksNotDone:
                        if allInputsReady(task):
                            self.assertNotIn(
                                runnerId,
                                (task.getRunners() or job.getRunners())
                                )

            for item in job.getTaskGroupSequence():
                if isinstance(item, taskgroup.TaskGroup):
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
                            self.assertEqual(task['runner'], runnerId)
                            noTasksDone = False
                        else:
                            tasksNotDone.append(task)
                    if taskRunners is None:
                        self.assertEqual(len(tasksNotDone), 0)
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
        self.randomRuns(runs, rnd, CustomGenerator, checkResults)

    def test0120CombinedProduct(self):
        '''Verifies that a combined product becomes available after all tasks
        that can produce it have run, whether those tasks end in "ok" or
        "error".
        '''

        class CustomGenerator(DataGenerator):
            pass
        gen = CustomGenerator()

        image = gen.createProduct('image', False, True)
        buildFw = gen.createFramework('build', [], [ image ])
        testFw = gen.createFramework('test', [ image ], [])
        buildTask1 = gen.createTask('build1', buildFw)
        buildTask2 = gen.createTask('build2', buildFw)
        testTask = gen.createTask('test', testFw)

        buildTR = gen.createTaskRunner('tr_build', gen.target, [ 'build' ])
        testTR = gen.createTaskRunner('tr_test', gen.target, [ 'test' ])

        def simulate(config):
            self.sanityCheck(gen, config)

            job = config.createJob(self.owner)
            # TODO: The toXML functionality should probably be tested
            #       in a separate test case.

            # Verify execution:
            # Successfully complete first build task.
            task = job.assignTask(resourcelib.taskRunnerDB[buildTR])
            self.assertIsNotNone(task)
            self.assertTrue(task.getName().startswith('build'))
            taskDone(job, task.getName())
            # Try to start test task (should fail).
            task = job.assignTask(resourcelib.taskRunnerDB[testTR])
            self.assertIsNone(task)
            # Complete second build task, but make it fail.
            task = job.assignTask(resourcelib.taskRunnerDB[buildTR])
            self.assertIsNotNone(task)
            self.assertTrue(task.getName().startswith('build'))
            taskDone(job, task.getName(), ResultCode.ERROR)
            # Try to start test task (should succeed).
            task = job.assignTask(resourcelib.taskRunnerDB[testTR])
            self.assertIsNotNone(task)
            self.assertEqual(task.getName(), testTask)
            # Successfully complete test task.
            taskDone(job, testTask)
            self.assertTrue(job.isExecutionFinished())
            self.assertTrue(job.hasFinalResult())
            # Check that locators have been stored separately.
            producers = set()
            for taskId, locator in job.getProduct(image).getProducers():
                self.assertTrue(taskId.startswith('build'))
                self.assertEqual(locator, locatorForTask(taskId))

        self.runWithReload(gen.createConfiguration(), simulate)

    def test0130PostponedInspection(self):
        '''Tests job execution where the results are not known at the time that
        the execution finishes.
        '''

        class CustomGenerator(DataGenerator):
            pass
        gen = CustomGenerator()

        image = gen.createProduct('image')
        buildFw = gen.createFramework('build', [], [ image ])
        testFw = gen.createFramework('test', [ image ], [])
        buildTask = gen.createTask('build', buildFw)
        testTask1 = gen.createTask('test1', testFw)
        testTask2 = gen.createTask('test2', testFw)
        testTask3 = gen.createTask('test3', testFw)

        tr = gen.createTaskRunner('tr_build', gen.target, [ 'build', 'test' ])

        def simulate(config):
            self.sanityCheck(gen, config)

            job = config.createJob(self.owner)
            # TODO: The toXML functionality should probably be tested
            #       in a separate test case.

            # Verify execution:
            # Successfully complete first build task.
            task = job.assignTask(resourcelib.taskRunnerDB[tr])
            self.assertIsNotNone(task)
            self.assertEqual(task.getName(), buildTask)
            taskDone(job, buildTask)
            self.assertEqual(job.getResult(), ResultCode.OK)
            self.assertEqual(job.getFinalResult(), None)
            # Successfully complete first test task, without result.
            task = job.assignTask(resourcelib.taskRunnerDB[tr])
            self.assertIsNotNone(task is not None)
            self.assertEqual(task.getName(), testTask1)
            taskDone(job, testTask1, ResultCode.INSPECT)
            self.assertFalse(job.isExecutionFinished())
            self.assertFalse(job.hasFinalResult())
            self.assertEqual(job.getResult(), ResultCode.INSPECT)
            self.assertIsNone(job.getFinalResult())
            # Successfully complete second test task, with result.
            task = job.assignTask(resourcelib.taskRunnerDB[tr])
            self.assertIsNotNone(task)
            self.assertEqual(task.getName(), testTask2)
            taskDone(job, testTask2, ResultCode.OK)
            self.assertFalse(job.isExecutionFinished())
            self.assertFalse(job.hasFinalResult())
            self.assertEqual(job.getResult(), ResultCode.INSPECT)
            self.assertIsNone(job.getFinalResult())
            # Successfully complete third test task, without result.
            task = job.assignTask(resourcelib.taskRunnerDB[tr])
            self.assertIsNotNone(task)
            self.assertEqual(task.getName(), testTask3)
            taskDone(job, testTask3, ResultCode.INSPECT)
            self.assertTrue(job.isExecutionFinished())
            self.assertFalse(job.hasFinalResult())
            self.assertEqual(job.getResult(), ResultCode.INSPECT)
            self.assertIsNone(job.getFinalResult())
            # Attempt to set invalid inspection result.
            with self.assertRaises(ValueError):
                job.inspectDone(testTask1, ResultCode.CANCELLED, 'invalid')
            # Complete inspection of first task.
            job.inspectDone(testTask1, ResultCode.WARNING, 'inspect 1')
            self.assertTrue(job.isExecutionFinished())
            self.assertFalse(job.hasFinalResult())
            self.assertEqual(job.getResult(), ResultCode.INSPECT)
            self.assertIsNone(job.getFinalResult())
            # Attempt to change inspection result.
            with self.assertRaises(IllegalStateError):
                job.inspectDone(testTask1, ResultCode.OK, 'invalid')
            # Complete inspection of third task.
            job.inspectDone(testTask3, ResultCode.OK, 'inspect 3')
            self.assertTrue(job.isExecutionFinished())
            self.assertTrue(job.hasFinalResult())
            self.assertEqual(job.getResult(), ResultCode.WARNING)
            self.assertEqual(job.getFinalResult(), ResultCode.WARNING)

        self.runWithReload(gen.createConfiguration(), simulate)

if __name__ == '__main__':
    unittest.main()

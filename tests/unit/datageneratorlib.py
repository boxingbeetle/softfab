# SPDX-License-Identifier: BSD-3-Clause

from io import StringIO
import random

from softfab.configlib import Task as ConfigTask
from softfab.frameworklib import Framework
from softfab.productdeflib import ProductDef
from softfab.resourcelib import RequestFactory
from softfab.resreq import ResourceSpec
from softfab.restypelib import ResType
from softfab.timelib import setTime
from softfab.xmlbind import parse


# Stop time, so Task Runner will not get out of sync.
setTime(1000)

def _addResources(record, resources):
    if resources is not None:
        for args in resources:
            spec = ResourceSpec.create(*args)
            record.addResourceSpec(spec)

class DataGenerator:
    # Default parameters; you can override these in a subclass.
    numTasks = 100
    numInputs = [ 0, 1, 1, 1, 2, 2, 3, 4 ]
    numOutputs = [ 0, 1, 1, 1, 2 ]
    chanceChainProduct = 0.8
    chanceLocalProduct = 0.5
    numTaskRunners = 1

    def __init__(self, dbs, rnd = None, run = 0):
        self.dbs = dbs
        if rnd is None:
            self.rnd = random.Random()
        else:
            self.rnd = rnd
        self.run = run
        self.owner = 'owner1'
        self.comment = 'this is a comment'
        self.products = []
        self.frameworks = []
        self.tasks = []
        self.inputsCreated = []
        self.taskRunners = []

    def createProduct(self, name, local = False, combined = False):
        productDefDB = self.dbs['productDefDB']
        product = ProductDef.create(name=name, local=local, combined=combined)
        productDefDB.add(product)
        self.products.append(name)
        return name

    def createRandomProduct(self):
        return self.createProduct(
            'product' + str(self.run) + '_' + str(len(self.products)),
            self.rnd.random() < self.chanceLocalProduct
            )

    def createFramework(self, name, inputs=(), outputs=(), resources=None):
        frameworkDB = self.dbs['frameworkDB']
        framework = Framework.create(name, inputs, outputs)
        _addResources(framework, resources)
        frameworkDB.add(framework)
        self.frameworks.append(name)
        return name

    def createTask(self, name, framework, resources=None):
        taskDefDB = self.dbs['taskDefDB']
        task = taskDefDB.factory.newTaskDef(name, framework)
        if resources is None:
            task.addTaskRunnerSpec(capabilities=(framework,))
        _addResources(task, resources)
        taskDefDB.add(task)
        self.tasks.append(name)
        return name

    def createResourceType(self, name=None, pertask=False, perjob=False):
        if name is None:
            name = 'restype%d' % len(self.dbs['resTypeDB'])
        resType = ResType.create(name, pertask, perjob)
        self.dbs['resTypeDB'].add(resType)
        return name

    def createResource(self, resType, capabilities=(), name=None):
        resourceDB = self.dbs['resourceDB']
        if name is None:
            name = 'resource%d' % len(resourceDB)
        resource = resourceDB.factory.newResource(
            name, resType, 'created by datageneratorlib', capabilities
            )
        resourceDB.add(resource)
        return name

    def createDefinitions(self):
        """Populate product, framework and task definition databases.
        """

        for taskCount in range(self.numTasks):
            # Determine input products.
            inputs = []
            for inputCount in range(self.rnd.choice(self.numInputs)):
                if len(self.products) == 0 \
                or self.rnd.random() >= self.chanceChainProduct:
                    # Create new product.
                    product = self.createRandomProduct()
                    self.inputsCreated.append(product)
                else:
                    # Re-use existing product.
                    product = self.rnd.choice(self.products)
                inputs.append(product)

            # Determine output products.
            outputs = []
            for outputCount in range(self.rnd.choice(self.numOutputs)):
                # Create new product.
                outputs.append(self.createRandomProduct())

            # Note: Always uses a separate framework for each task.
            #       Is that a serious weakness?
            framework = self.createFramework(
                'framework' + str(self.run) + '.' + str(len(self.frameworks)),
                inputs, outputs )

            # TODO: Add resources as well.
            task = self.createTask(
                'task' + str(self.run) + '.' + str(len(self.tasks)),
                framework )

    def createTaskRunnerData(self, name, target, versionStr):
        return parse(
            RequestFactory(),
            StringIO(
                '<request runnerId="' + name + '" '
                'runnerVersion="' + versionStr + '"/>'
            ))

    def createTaskRunner(self, *, name=None, target=None, capabilities=(),
                         versionStr='3.0.0'):
        jobDB = self.dbs['jobDB']
        resourceDB = self.dbs['resourceDB']
        if name is None:
            name = 'taskrunner%d_%d' % (self.run, len(resourceDB))
        capabilities = list(capabilities)
        if target is not None:
            capabilities.append(target)
        resourceFactory = resourceDB.factory
        taskRunner = resourceFactory.newTaskRunner(name, '', capabilities)
        resourceDB.add(taskRunner)
        data = self.createTaskRunnerData(name, target, versionStr)
        taskRunner.sync(jobDB, data)
        self.taskRunners.append(name)
        return name

    def createTaskRunners(self):
        """Create Task Runner records.
        """
        for _ in range(self.numTaskRunners):
            self.createTaskRunner(capabilities=self.frameworksForTaskRunner())

    def frameworksForTaskRunner(self):
        return self.frameworks

    def addCapabilities(self, config):
        """Add capabilities to Task Runners until all tasks are possible.
        """
        resourceDB = self.dbs['resourceDB']
        for task in config.getTaskGroupSequence():
            taskCaps = task.getNeededCaps()
            matches = []
            for trName in self.taskRunners:
                runnerCaps = resourceDB[trName].capabilities
                missingCaps = [
                    cap for cap in taskCaps
                    if cap not in runnerCaps
                    ]
                if missingCaps == []:
                    break
                matches.append( (len(missingCaps), missingCaps, trName) )
            else:
                num, missingCaps, trName = min(matches)
                taskRunner = resourceDB[trName]
                taskRunner.capabilities |= set(missingCaps)

    def createConfiguration(self, name=None, tasks=None, targets=()):
        """Create a job configuration.
        """

        if name is None:
            name = 'job' + str(self.run)

        if tasks is not None:
            tasksToAdd = set(self.tasks) & set(tasks)
        else:
            tasksToAdd = self.tasks
        tasksRandomOrder = list(tasksToAdd)
        self.rnd.shuffle(tasksRandomOrder)

        configDB = self.dbs['configDB']
        taskDefDB = self.dbs['taskDefDB']

        configFactory = configDB.factory
        config = configFactory.newConfig(
            name = name,
            targets = targets,
            owner = self.owner,
            trselect = False,
            comment = self.comment,
            jobParams = {},
            tasks = (
                ConfigTask.create(
                    name = taskId,
                    priority = 0,
                    taskDef = taskDefDB[taskId],
                    parameters = {},
                    )
                for taskId in tasksRandomOrder
                ),
            runners = set()
            )

        configDB.add(config)
        return config

    def setInputs(self, config):
        """Provide locators for the inputs.
        """
        resourceDB = self.dbs['resourceDB']
        mainGroup = config._getMainGroup()
        for group, inputs in config.getInputsGrouped():
            if group is None:
                # Global product, so not bound to a single Runner.
                taskRunner = None
            else:
                taskCaps = set(group.getNeededCaps())
                capableRunners = [
                    taskRunnerId
                    for taskRunnerId in self.taskRunners
                    if taskCaps.issubset(resourceDB[taskRunnerId].capabilities)
                    ]
                taskRunner = self.rnd.choice(capableRunners)
            for inp in inputs:
                inp.setLocator('dummylocator', taskRunner)

        # TODO: This should not be necessary.
        config._notify()


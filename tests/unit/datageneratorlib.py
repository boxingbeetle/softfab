# SPDX-License-Identifier: BSD-3-Clause

import configlib, frameworklib, productdeflib, resourcelib, restypelib, \
    taskdeflib, taskrunnerlib, userlib, xmlbind
from resreq import ResourceSpec

from io import StringIO
import os, os.path, random

def removeRec(path):
    """Removes a directory and the files it contains, recursively.
    """
    if os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        for file in os.listdir(path):
            removeRec(path + '/' + file)
        os.rmdir(path)
    else:
        assert False, path

def _addResources(record, resources):
    if resources is not None:
        for args in resources:
            spec = ResourceSpec.create(*args)
            record.addResourceSpec(spec)

class DataGenerator(object):
    # Default parameters; you can override these in a subclass.
    numTasks = 100
    numInputs = [ 0, 1, 1, 1, 2, 2, 3, 4 ]
    numOutputs = [ 0, 1, 1, 1, 2 ]
    chanceChainProduct = 0.8
    chanceLocalProduct = 0.5
    numTaskRunners = 1

    def __init__(self, rnd = None, run = 0):
        if rnd is None:
            self.rnd = random.Random()
        else:
            self.rnd = rnd
        self.run = run
        self.target = 'target1'
        self.owner = 'owner1'
        self.comment = 'this is a comment'
        self.products = []
        self.frameworks = []
        self.tasks = []
        self.inputsCreated = []
        self.taskRunners = []

    def createProduct(self, name, local = False, combined = False):
        product = productdeflib.ProductDef.create(
            name=name, local=local, combined=combined
            )
        productdeflib.productDefDB.add(product)
        self.products.append(name)
        return name

    def createRandomProduct(self):
        return self.createProduct(
            'product' + str(self.run) + '_' + str(len(self.products)),
            self.rnd.random() < self.chanceLocalProduct
            )

    def createFramework(self, name, inputs=(), outputs=(), resources=None):
        framework = frameworklib.Framework.create(name, inputs, outputs)
        _addResources(framework, resources)
        frameworklib.frameworkDB.add(framework)
        self.frameworks.append(name)
        return name

    def createTask(self, name, framework, resources=None):
        task = taskdeflib.TaskDef.create(name, framework)
        if resources is None:
            task.addTaskRunnerSpec(capabilities=(framework,))
        _addResources(task, resources)
        taskdeflib.taskDefDB.add(task)
        self.tasks.append(name)
        return name

    def createResourceType(self, name=None, pertask=False, perjob=False):
        if name is None:
            name = 'restype%d' % len(restypelib.resTypeDB)
        resType = restypelib.ResType.create(name, pertask, perjob)
        restypelib.resTypeDB.add(resType)
        return name

    def createResource(self, resType, capabilities=(), name=None):
        if name is None:
            name = 'resource%d' % len(resourcelib.resourceDB)
        resource = resourcelib.Resource.create(
            name, resType, 'location:%s/%s' % (resType, name),
            'created by datageneratorlib', capabilities
            )
        resourcelib.resourceDB.add(resource)
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
        return xmlbind.parse(
            taskrunnerlib.RequestFactory(),
            StringIO(
                '<request runnerId="' + name + '" '
                'runnerVersion="' + versionStr + '">'
                    '<target name="' + target + '"/>'
                '</request>'
            ))

    def createTaskRunner(
        self, name, target, capabilities, versionStr = '2.0.0'
        ):
        data = self.createTaskRunnerData(name, target, versionStr)
        taskRunner = taskrunnerlib.TaskRunner.create(data)
        taskRunner.capabilities = capabilities
        taskrunnerlib.taskRunnerDB.add(taskRunner)
        taskRunner.sync(data)
        self.taskRunners.append(name)
        return name

    def createTaskRunners(self):
        """Create Task Runner records.
        """

        for count in range(self.numTaskRunners):
            self.createTaskRunner(
                'taskrunner'+ str(self.run) + '_' + str(count),
                self.target,
                self.frameworksForTaskRunner()
                )

    def frameworksForTaskRunner(self):
        return self.frameworks

    def addCapabilities(self, config):
        """Add capabilities to Task Runners until all tasks are possible.
        """
        for task in config.getTaskGroupSequence():
            taskCaps = task.getNeededCaps()
            matches = []
            for trName in self.taskRunners:
                runnerCaps = taskrunnerlib.taskRunnerDB[trName].capabilities
                missingCaps = [
                    cap for cap in taskCaps
                    if cap not in runnerCaps
                    ]
                if missingCaps == []:
                    break
                matches.append( (len(missingCaps), missingCaps, trName) )
            else:
                num, missingCaps, trName = min(matches)
                taskRunner = taskrunnerlib.taskRunnerDB[trName]
                taskRunner.capabilities |= set(missingCaps)

    def createConfiguration(self, name = None, tasks = None):
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

        config = configlib.Config.create(
            name = name,
            target = self.target,
            owner = self.owner,
            trselect = False,
            comment = self.comment,
            jobParams = {},
            tasks = (
                configlib.Task.create(
                    name = taskId,
                    priority = 0,
                    parameters = {},
                    )
                for taskId in tasksRandomOrder
                ),
            runners = set(),
            )

        configlib.configDB.add(config)
        return config

    def setInputs(self, config):
        """Provide locators for the inputs.
        """
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
                    if taskCaps.issubset(
                        taskrunnerlib.taskRunnerDB[taskRunnerId].capabilities
                        )
                    ]
                taskRunner = self.rnd.choice(capableRunners)
            for inp in inputs:
                inp.setLocator('dummylocator', taskRunner)

        # TODO: This should not be necessary.
        config._notify()


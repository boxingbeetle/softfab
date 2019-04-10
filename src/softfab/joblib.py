# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from typing import TYPE_CHECKING, List, Sequence, cast
import logging

from softfab import frameworklib, taskdeflib, taskrunlib
from softfab.config import dbDir
from softfab.databaselib import (
    Database, DatabaseElem, RecordObserver, createUniqueId
)
from softfab.dispatchlib import pickResources
from softfab.paramlib import specialParameters
from softfab.productlib import Product, productDB
from softfab.resourcelib import resourceDB
from softfab.resreq import ResourceClaim, ResourceSpec
from softfab.restypelib import resTypeDB
from softfab.resultcode import combineResults
from softfab.taskgroup import PriorityMixin, TaskSet
from softfab.tasklib import (
    ResourceRequirementsMixin, TaskRunnerSet, TaskStateMixin
)
from softfab.timelib import getTime
from softfab.waiting import (
    InputReason, ReasonForWaiting, ResourceMissingReason, checkRunners
)
from softfab.xmlbind import XMLTag
from softfab.xmlgen import xml

if TYPE_CHECKING:
    from softfab.resourcelib import TaskRunner
else:
    TaskRunner = object


class JobFactory:
    @staticmethod
    def createJob(attributes):
        return Job(attributes)

class JobDB(Database):
    baseDir = dbDir + '/jobs'
    factory = JobFactory()
    privilegeObject = 'j'
    description = 'job'
    cachedUniqueValues = ( 'owner', 'target' )
    uniqueKeys = ( 'recent', 'jobId' )

    def convert(self, visitor=None):
        # Find orphaned products.
        orphanedProductIDs = set(productDB.keys())
        def checkJob(job):
            if visitor:
                visitor(job)
            for product in job.getInputs() + job.getProduced():
                orphanedProductIDs.discard(product.getId())

        super().convert(checkJob)

        if orphanedProductIDs:
            logging.warning(
                'Removing %d obsolete product(s)...', len(orphanedProductIDs)
                )
            for productID in orphanedProductIDs:
                productDB.remove(productDB[productID])

jobDB = JobDB()
taskrunlib.jobDB = jobDB

def unifyJobId(jobId):
    if jobId[4] == '-':
        return jobId[2 : 4] + jobId[5 : 7] + jobId[8 : 10] + '-' + \
            jobId[11 : 13] + jobId[14 : 16] + '-' + jobId[17 : ]
    else:
        return jobId

class Task(
        PriorityMixin, ResourceRequirementsMixin, TaskStateMixin,
        XMLTag, TaskRunnerSet
        ):
    tagName = 'task'
    intProperties = ('priority', )

    @staticmethod
    def create(job, name, priority, runners):
        tdKey = taskdeflib.taskDefDB.latestVersion(name)
        fdKey = frameworklib.frameworkDB.latestVersion(
                taskdeflib.taskDefDB.getVersion(tdKey)['parent']
                )

        properties = dict(
            name = name,
            priority = priority,
            tdKey = tdKey,
            fdKey = fdKey,
            )
        task = Task(properties, job)
        # pylint: disable=protected-access
        task._setRunners(runners)
        return task

    def __init__(self, attributes, job):
        XMLTag.__init__(self, attributes)
        TaskRunnerSet.__init__(self)
        TaskStateMixin.__init__(self)
        self._properties.setdefault('priority', 0)
        self._parameters = {}
        self.__taskRun = None
        self.__job = job

    def __getitem__(self, key):
        if key in self._properties:
            return self._properties[key]
        elif key in ['target', 'owner', 'timestamp', 'jobId']:
            return self.__job[key]
        elif key == 'duration':
            return self.getDuration()
        elif key == 'parameters':
            return sorted(
                param for param in self.getParameters()
                if param not in specialParameters
                )
        else:
            return self.getLatestRun()[key]

    def _addParam(self, attributes):
        self.addParameter(attributes['name'], attributes['value'])

    def addParameter(self, key, value):
        # Only store non-default values.
        framework = self.getFramework()
        getParent = lambda key: framework
        if self.getDef().getParameter(key, getParent) != value:
            self._parameters[key] = value

    def initCached(self, resultOnly):
        '''Store selected data items from TaskRun in Task, so we do not have
        to load TaskRun objects for the most common queries.
        TODO: Well, that was the original idea, but we are preloading the
              taskRunDB, so was it an unrealistic idea, are we loading this
              DB unnecessarily or is it necessary now but not with a few
              implementation changes?
        '''
        taskRun = self.getLatestRun()
        if not resultOnly:
            for key in ['state', 'starttime', 'stoptime']:
                self._properties[key] = taskRun[key]
        result = taskRun['result']
        if result is not None:
            self._properties['result'] = result
        self.__job._notify()

    def isGroup(self):
        return False

    def getJob(self):
        return self.__job

    def getLatestRun(self):
        # Note: Because of caching __taskRun there is a reference loop, which
        #       has to be broken if the objects are to be removed from memory.
        if self.__taskRun is None:
            taskRun = taskrunlib.taskRunDB[self._properties['run']]
            self.__taskRun = taskRun
        return self.__taskRun #taskRun

    def getRun(self, runId):
        # This is a temporary implementation until we add support for multiple
        # runs of the same task.
        if runId == '0':
            return self.getLatestRun()
        else:
            raise KeyError(runId)

    def getDef(self):
        return taskdeflib.taskDefDB.getVersion(self._properties['tdKey'])

    def getFramework(self):
        return frameworklib.frameworkDB.getVersion(self._properties['fdKey'])

    def getName(self) -> str:
        return cast(str, self._properties['name'])

    def getPriority(self) -> int:
        return cast(int, self._properties['priority'])

    def hasExtractionWrapper(self):
        # TODO: Getting the property from the task def would cause an
        #       unversioned lookup of the framework, which is wrong in the
        #       context of a job. As a workaround, we get the property directly
        #       from the framework.
        return self.getFramework()['extract']

    def newRun(self):
        self.__taskRun = taskrunlib.newTaskRun(self)
        self._properties['run'] = self.__taskRun.getId()

    def _getContent(self):
        for name, value in self._parameters.items():
            yield xml.param(name = name, value = value)
        yield self.runnersAsXML()

    def getInputs(self):
        return self.getFramework().getInputs()

    def getOutputs(self):
        return self.getFramework().getOutputs()

    def getDependencies(self):
        # TODO: Different terminology: input/dependency and output/produced.
        return [ self.__job.getProduct(inp) for inp in self.getInputs() ]

    def getParameter(self, name):
        '''Gets the value of the parameter with the given name in this task run.
        Returns None in case no parameter with that name exists.
        A parameter is a key-value pair that is interpreted by the wrapper.
        '''
        value = self._parameters.get(name)
        if value is None:
            framework = self.getFramework()
            getParent = lambda key: framework
            return self.getDef().getParameter(name, getParent)
        else:
            return value

    def isFinal(self, name):
        '''Returns True iff the given parameter is final.
        '''
        framework = self.getFramework()
        getParent = lambda key: framework
        return self.getDef().isFinal(name, getParent)

    def getParameters(self):
        '''Returns a new dictionary containing the parameters of this task.
        '''
        framework = self.getFramework()
        getParent = lambda key: framework
        parameters = self.getDef().getParameters(getParent)
        parameters.update(self._parameters)
        return parameters

    def getVisibleParameters(self):
        '''Returns a new dictionary of parameters to be shown to the user:
        final and reserved parameters are not included.
        '''
        taskDef = self.getDef()
        framework = self.getFramework()
        getParent = lambda key: framework
        parameters = taskDef.getParameters(getParent)
        parameters.update(self._parameters)
        return dict(
            ( key, value )
            for key, value in parameters.items()
            if not key.startswith('sf.') and not taskDef.isFinal(key, getParent)
            )

    def canRunOn(self, runner):
        if self._runners:
            return runner in self._runners
        else:
            return self.__job.canRunOn(runner)

    def _getState(self):
        return self['state']

    def getResult(self):
        return self._properties.get('result') or self.getLatestRun().getResult()

    def getDuration(self):
        startTime = self._properties.get('starttime')
        stopTime = self._properties.get('stoptime')
        if startTime is not None and stopTime is None:
            return stopTime - startTime
        else:
            return self.getLatestRun().getDuration()

    # The following methods forward calls to the last (currently the only)
    # TaskRun. This may not be appropriate when having multiple task runs.
    # Thus run ID should be passed as a parameter where appropriate.

    def getProduced(self):
        return self.getLatestRun().getProduced()

    def getSummaryHTML(self):
        return self.getLatestRun().getSummaryHTML()

    def assign(self, taskRunner):
        taskRun = self.getLatestRun()
        if not taskRun.isWaiting():
            return None

        if not all(product.isAvailable() for product in self.getDependencies()):
            return None

        neededCaps = self.getNeededCaps()
        runners = self.getRunners() or self.__job.getRunners()
        if runners and taskRunner.getId() not in runners:
            return None
        elif not neededCaps.issubset(taskRunner.capabilities):
            return None
        else:
            return taskRun.assign(taskRunner)

    def checkRunners(self,
                     taskRunners: Sequence[TaskRunner],
                     whyNot: List[ReasonForWaiting]
                     ) -> None:
        taskRun = self.getLatestRun()
        if not taskRun.isWaiting():
            return

        waitingFor = [
            product.getName()
            for product in self.getDependencies()
            if not product.isAvailable()
            ]
        if waitingFor:
            whyNot.append(InputReason(waitingFor))

        neededCaps = self.getNeededCaps()
        runners = self.getRunners() or self.__job.getRunners()
        if runners:
            candidates = [
                runner for runner in taskRunners
                if runner.getId() in runners
                ] # type: Sequence[TaskRunner]
        else:
            candidates = taskRunners
        checkRunners(candidates, self.__job['target'], neededCaps, whyNot)

        taskRun.checkResources(whyNot)

    def abort(self, user = None):
        return self.getLatestRun().abort(user)

    def done(self, result, summary, outputs):
        return self.getLatestRun().done(result, summary, outputs)

    def inspectDone(self, result, summary):
        return self.getLatestRun().inspectDone(result, summary)

    def cancelled(self, summary):
        return self.getLatestRun().cancelled(summary)

    def setURL(self, url):
        return self.getLatestRun().setURL(url)

    def getURL(self):
        return self.getLatestRun().getURL()

    def getExportURL(self):
        return self.getLatestRun().getExportURL()

    def hasExport(self):
        return self.getLatestRun().hasExport()

    def getRunId(self):
        return self.getLatestRun().getRunId()

    def setAlert(self, alert):
        return self.getLatestRun().setAlert(alert)

    def getAlert(self):
        return self.getLatestRun().getAlert()

class Job(TaskSet, TaskRunnerSet, XMLTag, DatabaseElem):
    '''A collection of tasks and their input and output products.
    Contains information about what should be executed,
    what has been executed and what the result was.
    '''
    tagName = 'job'
    intProperties = ('timestamp', )

    @staticmethod
    def create(configId, target, owner, comment, jobParams, runners):
        # TODO: Is validation needed?
        properties = dict(
            jobId = createUniqueId(),
            timestamp = getTime(),
            target = target,
            )
        if owner is not None:
            properties['owner'] = owner
        if configId is not None:
            properties['configId'] = configId

        job = Job(properties)
        job.comment = comment
        # pylint: disable=protected-access
        job.__params.update(jobParams)
        job._setRunners(runners)
        return job

    def __init__(self, properties):
        # Note: if the "comment" tag is empty, the XML parser does not call the
        #       <text> handler, so we have to use '' rather than None here.
        TaskSet.__init__(self)
        TaskRunnerSet.__init__(self)
        XMLTag.__init__(self, properties)
        DatabaseElem.__init__(self)
        self.__comment = ''
        self.__inputSet = None
        self.__products = {}
        self.__params = {}
        self.__mainGroup = None
        self.__description = None
        self.__result = None
        self.__leadTime = None
        self.__stopTime = None
        self.__executionFinished = False
        self.__resultFinal = False
        self.__inputs = None # Cached value of getInputs.
        self.__produced = None # Cached value of getProduced.
        self.__notifyFlag = None
        self.__taskSequence = []
        # __resources: { ref: [set(tasks), set(caps), id], ... }
        self.__resources = defaultdict(lambda: [ set(), set(), None ])

        # Create a sort key which places the most recent jobs first.
        # This code ignores the fact that the job IDs converted from the old
        # format are two characters longer than the new ones, therefore the old
        # jobs will always have greater reversed ID, which is no problem in
        # this particular case, but might not work as expected in general.
        self.__recent = int(''.join(
            '%1X' % (15 - int(char, 16))
            for char in unifyJobId(self.getId())
            if char != '-'
            ), 16)

    def __str__(self):
        return 'job[' + self.getId() + ']'

    def __getitem__(self, key):
        if key == 'recent':
            return self.__recent
        elif key == 'leadtime':
            return self.getLeadTime()
        elif key == 'description':
            return self.getDescription()
        elif key == 'owner':
            return self.getOwner()
        elif key == 'scheduledby':
            return self.getScheduledBy()
        elif key == 'configId':
            return self.getConfigId()
        else:
            return XMLTag.__getitem__(self, key)

    def __addTask(self, task):
        name = task.getName()
        self._tasks[name] = task
        self.__taskSequence.append(name)
        # Examine task resource requirements
        for spec in task.resourceClaim:
            typeObj = resTypeDB.get(spec.typeName)
            if typeObj is not None and typeObj['perjob']:
                tasks, caps, _ = self.__resources[spec.reference]
                # TODO: We don't understand exactly what this code does.
                #       Major refactoring is needed urgently.
                #
                # We avoid calling any methods on a task which cause an access
                # to the task run, because the run must not be loaded;
                # it might not exist yet, or it might trigger an infinite
                # recursion when it tries to access the job it belongs to.
                #
                # This code relies on the task always having 'state' cached if
                # it is fixed, which is currently true, but not future-proof.
                taskState = task._properties.get('state')
                if taskState is None or not task.isExecutionFinished():
                    tasks.add(name)
                caps.update(spec.capabilities)
        return task

    def __lockNotify(self):
        assert self.__notifyFlag is None
        self.__notifyFlag = False

    def __unlockNotify(self):
        if self.__notifyFlag:
            DatabaseElem._notify(self)
        self.__notifyFlag = None

    def _notify(self):
        if self.__notifyFlag is None:
            DatabaseElem._notify(self)
        else:
            self.__notifyFlag = True

    def _textComment(self, text):
        self.__comment = text

    def _addTask(self, attributes):
        return self.__addTask(Task(attributes, self))

    def _addProduct(self, attributes):
        self.__products[attributes['name']] = attributes['key']

    def _addResource(self, attributes):
        self.__resources[attributes['ref']][2] = attributes.get('id') or None

    def getId(self):
        return self._properties['jobId']

    def __checkProduct(self, name):
        if not name in self.__products:
            self.__products[name] = Product.create(name).getId()

    def _addParam(self, attributes):
        self.__params[attributes['name']] = attributes['value']

    def addTask(self, name, prio, runners):
        '''Adds a run of the task by the given name to this job.
        Also adds all input and output products of that task, in state
        "waiting".
        This method is only intended for Config.createJob(), which should
        add the tasks in the right order.
        '''
        task = Task.create(job=self, name=name, priority=prio, runners=runners)
        self.__addTask(task).newRun()
        productNames = task.getInputs() | task.getOutputs()
        for productName in productNames:
            self.__checkProduct(productName)
        return task

    @property
    def comment(self):
        """User-specified comment string for this job.
        Comment string may contain newlines.
        Setting the comment will strip leading and trailing whitespace.
        """
        return self.__comment

    @comment.setter
    def comment(self, comment):
        self.__comment = comment.strip()

    def getParams(self):
        return self.__params

    def getTarget(self):
        '''Gets the target of this job.
        '''
        return self._properties['target']

    def getOwner(self):
        """Gets the owner of this job,
        or None if this job does not have an owner.
        """
        return self._properties.get('owner')

    def getScheduledBy(self):
        """Gets the way of starting of this job,
        or None if this job is started manually
        """
        return self._properties.get('scheduledby')

    def setScheduledBy(self, job):
        """ Sets the way of starting this job,
        or None if this job is started manually
        """
        self._properties['scheduledby'] = job

    def _isProductFixed(self, product):
        '''Returns True iff all tasks that produce the given product are fixed.
        Used to determine when a combined product is available, or when to
        give up on a non-combined product.
        '''
        return all(
            task.isExecutionFinished()
            for task in self.getProducers(product.getName())
            )

    def _blockProduct(self, product):
        product.blocked()
        productName = product.getName()
        for task in self.getConsumers(productName):
            if task.isWaiting():
                task.cancelled(productName + ' is not available')

    def _getContent(self):
        if self.__comment:
            yield xml.comment[ self.__comment ]
        for key, value in self.__params.items():
            yield xml.param(name = key, value = value)
        for task in self.__taskSequence:
            yield self._tasks[task]
        for name, key in self.__products.items():
            yield xml.product(name = name, key = key)
        yield self.runnersAsXML()
        for ref, (_, _, resId) in self.__resources.items():
            yield xml.resource(ref = ref, id = resId)

    def isCompleted(self):
        '''Returns True iff all tasks in this job have run and have a result.
        '''
        return all(
            task.isDone() and task.hasResult()
            for task in self._tasks.values()
            )

    def isExecutionFinished(self):
        '''Returns True iff execution of all tasks in this job is finished.
        Note that a job that has finished execution might not have its result
        available yet if it is waiting for extraction or inspection.
        '''
        if not self.__executionFinished:
            self.__executionFinished = all(
                task.isExecutionFinished()
                for task in self._tasks.values()
                )
        return self.__executionFinished

    def hasFinalResult(self):
        '''Returns True iff the final result of this job is available.
        '''
        if not self.__resultFinal:
            self.__resultFinal = all(
                task.hasResult()
                for task in self._tasks.values()
                )
        return self.__resultFinal

    def _getMainGroup(self):
        if self.__mainGroup is None:
            self.__mainGroup = super()._getMainGroup()
        return self.__mainGroup

    def getTaskSequence(self):
        return [ self._tasks[task] for task in self.__taskSequence ]

    def iterTasks(self):
        '''Yields the tasks in this job, in arbitrary order.
        '''
        return iter(self._tasks.values())

    def getConfigId(self):
        """Return the ID of the configuration this job was once created from,
        or None if this job was created from scratch.
        """
        return self._properties.get('configId')

    def getDescription(self):
        # Since task definition is fixed, caching is possible.
        if self.__description is None:
            self.__description = self._properties.get('configId') or \
                                 super().getDescription()
        return self.__description

    def canRunOn(self, runner):
        if self._runners:
            return runner in self._runners
        else:
            return True

    def getFinalResult(self):
        '''Returns the ResultCode of the final result of this job, or None if
        this job does not have a final result yet.
        '''
        return self.getResult() if self.hasFinalResult() else None

    def getResult(self):
        '''Summarizes the current result of this job by combining the task
        results into a single value.
        The result returned by this method applies to the current situation
        and might change in the future; if that is not what you want, use
        getFinalResult() instead.
        '''
        if self.__result is not None:
            return self.__result
        result = combineResults(self._tasks.values())
        if self.hasFinalResult():
            self.__result = result
        return result

    def getRecent(self):
        return self.__recent

    def getCreateTime(self):
        return self._properties['timestamp']

    def getLeadTime(self):
        '''Gets the number of seconds elapsed between the creation of this job
        and its stop time. If the job is not stopped yet, the number of seconds
        elapsed until now is returned.
        '''
        leadTime = self.__leadTime
        if leadTime is not None:
            return leadTime
        queueTime = self.getCreateTime()
        if queueTime is None:
            return None
        stopTime = self.getStopTime()
        if stopTime is None:
            return getTime() - queueTime
        else:
            self.__leadTime = stopTime - queueTime
            return self.__leadTime

    def getStopTime(self):
        '''Gets this job's stop time, or None if it has not stopped yet.
        '''
        if self.__stopTime is None and self.isExecutionFinished():
            self.__stopTime = max(
                task['stoptime'] for task in self._tasks.values()
                )
        return self.__stopTime

    def getInputSet(self):
        if self.__inputSet is None:
            self.__inputSet = super().getInputSet()
        return self.__inputSet

    def getInputs(self):
        """Returns the list of input products of this job.
        """
        if self.__inputs is None:
            self.__inputs = [
                self.getProduct(inputName)
                for inputName in self.getInputSet()
                ]
        return self.__inputs

    def getProduced(self):
        '''Returns the list of products produced by this job, in the most
        likely creation order.
        '''
        if self.__produced is None:
            self.__produced = produced = []
            producedNames = set()
            for task in self.getTaskSequence():
                taskProduced = {}
                for product in task.getProduced():
                    name = product.getName()
                    if name not in producedNames:
                        taskProduced[name] = product
                for name, product in sorted(taskProduced.items()):
                    producedNames.add(name)
                    produced.append(product)
        return self.__produced

    def setInputLocator(self, name, locator, taskRunner, taskName):
        '''Mark an input as available and provide its locator.
        The taskName parameter provides a fake task name for the producer.
        Raises ValueError if `taskRunner` is None for a local product.
        '''
        assert name in self.getInputSet(), \
            '%s not in %s' % ( name, self.getInputSet() )
        assert locator is not None
        product = self.getProduct(name)
        if taskRunner is None and product.isLocal():
            raise ValueError(
                'No Task Runner specified for local product "%s"' % name
                )
        product.done()
        product.storeLocator(locator, taskName)
        if product.isLocal():
            product.setLocalAt(taskRunner)

    def assignTask(self, taskRunner):
        '''Tries to assign a task in this job to the given Task Runner.
        Returns the task assigned, or None if no task could be assigned.
        '''
        assigned = self._getMainGroup().assign(taskRunner)
        if assigned is not None:
            # TODO: We need real transactions, because reserved resources will
            #       never be freed if the job (later task run) is not committed.
            self._notify()
        return assigned

    def updateSummaries(self, taskRunners):
        """Updates the summaries for the waiting tasks in this job.
        You can get the new summaries using the TaskRun.getSummary().
        """
        if not self.isExecutionFinished():
            whyNot = []
            self._getMainGroup().checkRunners(taskRunners, whyNot)

    def taskDone(self, name, result, summary, outputs):
        """Marks a task as done and stores the result.
        """
        if not self.isExecutionFinished():
            self.__lockNotify()
            try:
                self._tasks[name].done(result, summary, outputs)
            finally:
                self.__unlockNotify()

    def inspectDone(self, name, result, summary):
        '''Stores result of a postponed inspection.
        '''
        self._tasks[name].inspectDone(result, summary)

    def abortTask(self, name, user = None):
        """Abort the task with the given name.
        Returns a message intended for the user that describes the result.
        """
        task = self._tasks[name]
        self.__lockNotify()
        try:
            changed_, message = task.abort(user)
        finally:
            self.__unlockNotify()
        return message

    def abortAll(self, taskFilter = lambda t: True, user = None):
        """Abort multiple tasks in this job.
        The given filter function is called with each task object;
        if the function returns True, that task is aborted.
        The default filter aborts all tasks.
        Returns set of aborted task names.
        """
        tasks = list(self.getTaskSequence())
        abortedTaskNames = set()
        self.__lockNotify()
        try:
            # Note: To avoid dependencies getting blocked before they can be
            #       aborted, start with tasks at the end of the dependency
            #       graph.
            for task in reversed(tasks):
                if taskFilter(task):
                    changed, message_ = task.abort(user)
                    if changed:
                        abortedTaskNames.add(task.getName())
        finally:
            self.__unlockNotify()
        return abortedTaskNames

    def getProduct(self, name):
        '''Returns the product with the given name.
        Raises KeyError if there is no product with the given name in this job.
        '''
        return productDB[self.__products[name]]

    def getProductDef(self, name):
        # Go through the Product object to get the correct version.
        return self.getProduct(name).getDef()

    def getProductLocation(self, name):
        return self.getProduct(name).getLocalAt()

    def reserveResources(self, claim, user, whyNot):
        if self.__resources:
            reserved = {}
            toReserve = []
            keepPerJob = []
            for spec in claim:
                ref = spec.reference
                resType = spec.typeName
                info = self.__resources.get(ref)
                if info is not None:
                    _, caps, resId = info
                    specCaps = spec.capabilities
                    assert caps >= specCaps
                    if resId is not None:
                        reserved[ref] = resId
                    else:
                        keepPerJob.append(ref)
                        if caps != specCaps:
                            spec = ResourceSpec.create(ref, resType, caps)
                        toReserve.append(spec)
                else:
                    toReserve.append(spec)
            reservedPerJob = {}
            for ref, resId in reserved.items():
                resource = resourceDB.get(resId)
                if resource is not None:
                    reservedPerJob[ref] = resource
                else:
                    if whyNot is not None:
                        # TODO: report multiple resources at the same time
                        whyNot.append(ResourceMissingReason(resId))
                    return None
            user = 'J-' + self.getId()
            resources = _reserveResources(
                ResourceClaim.create(toReserve), user, whyNot
                )
            if resources is not None:
                for ref in keepPerJob:
                    self.__resources[ref][2] = resources[ref].getId()
                resources.update(reservedPerJob)
            return resources
        else:
            return _reserveResources(claim, user, whyNot)

    def releaseResources(self, task, reserved):
        if self.__resources:
            toRelease = dict(reserved or ())
            for spec in task.resourceClaim:
                ref = spec.reference
                info = self.__resources.get(ref)
                if info is not None:
                    tasks, _, resId = info
                    tasks.remove(task.getName())
                    if not tasks:
                        toRelease[ref] = resId
                        info[2] = None
                    elif ref in toRelease:
                        del toRelease[ref]
                    if reserved is not None:
                        assert reserved[ref] == resId
            if toRelease:
                _releaseResources(toRelease.values())
        elif reserved is not None:
            _releaseResources(reserved.values())

def _reserveResources(claim, user, whyNot=None):
    assignment = pickResources(claim, resourceDB, whyNot)
    if assignment is not None:
        for resource in assignment.values():
            resource.reserve(user)
    return assignment

def _releaseResources(reserved):
    for resId in reserved:
        res = resourceDB.get(resId)
        if res is not None:
            res.free()

JobDB.keyRetrievers = {
    'recent': Job.getRecent,
    'timestamp': Job.getCreateTime,
    'leadtime': Job.getLeadTime,
    'target': Job.getTarget,
    'description': Job.getDescription,
    'owner': Job.getOwner,
    'configId': Job.getConfigId,
    }

class _TaskToJobs(RecordObserver):
    '''For each task ID, keep track of the IDs of all jobs containing that task.
    '''
    def __init__(self):
        RecordObserver.__init__(self)
        self.__taskToJobs = None

    def __call__(self, taskId):
        '''Iterates through all task objects with the given task ID.
        '''
        # Delayed initialization
        if self.__taskToJobs is None:
            self.__taskToJobs = defaultdict(list)
            # TODO: Initialising like this forces loading of the entire job DB.
            for job in jobDB:
                self.added(job)
            jobDB.addObserver(self)
        # TODO: Is the following comment still valid?
        # We maintain a dictionary of job IDs so we don't have to load all jobs.
        # However, anyone calling this function will most likely need to request
        # info about the tasks, so we return objects instead of IDs. Since we
        # use objects only at the last stage, only a selected few jobs are
        # loaded.
        return (
            jobDB[jobId].getTask(taskId)
            for jobId in self.get(taskId)
            )

    def get(self, taskId):
        # TODO: It would be nice to be able to raise KeyError if the definition
        #       of the task ID never existed (as opposed to no existing run).
        return self.__taskToJobs.get(taskId, [])

    def added(self, record):
        taskToJobs = self.__taskToJobs
        jobId = record.getId()
        for taskName in record.iterTaskNames():
            taskToJobs[taskName].append(jobId)

    def removed(self, record):
        assert False, 'jobs should not be removed'

    def updated(self, record):
        # We don't care, since the set of tasks will not be different.
        pass

getAllTasksWithId = _TaskToJobs()

def iterAllTasks(taskFilter):
    return (
        task
        for taskId in taskFilter
        for task in getAllTasksWithId(taskId)
        )

def iterDoneTasks(taskFilter):
    return (
        task
        for task in iterAllTasks(taskFilter)
        if task.isDone()
        )

def iterFinishedTasks(taskFilter):
    return (
        task
        for task in iterAllTasks(taskFilter)
        if task.hasResult()
        )

def iterUnfinishedTasks(taskFilter):
    return (
        task
        for task in iterAllTasks(taskFilter)
        if not task.hasResult()
        )

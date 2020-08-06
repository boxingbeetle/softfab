# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from pathlib import Path
from time import localtime
from typing import (
    TYPE_CHECKING, AbstractSet, Callable, DefaultDict, Dict, Iterable,
    Iterator, List, Mapping, MutableSet, Optional, Sequence, Tuple, Union, cast
)

from softfab import taskrunlib
from softfab.config import dbDir
from softfab.databaselib import (
    Database, DatabaseElem, RecordObserver, Retriever, createUniqueId
)
from softfab.dispatchlib import pickResources
from softfab.paramlib import specialParameters
from softfab.productlib import Product, ProductDB
from softfab.resourcelib import ResourceDB
from softfab.resreq import ResourceClaim, ResourceSpec
from softfab.restypelib import ResTypeDB
from softfab.sortedqueue import SortedQueue
from softfab.taskgroup import PriorityMixin, TaskSet
from softfab.tasklib import (
    ResourceRequirementsMixin, TaskRunnerSet, TaskStateMixin
)
from softfab.timelib import getTime
from softfab.utils import Comparable
from softfab.waiting import (
    InputReason, ReasonForWaiting, ResourceMissingReason, StatusLevel,
    TRStateReason, checkRunners
)
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLAttributeValue, XMLContent, xml

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from softfab.frameworklib import Framework, FrameworkDB
    from softfab.productdeflib import ProductDef
    from softfab.resourcelib import Resource, TaskRunner
    from softfab.resultcode import ResultCode
    from softfab.taskdeflib import TaskDef, TaskDefDB
    from softfab.taskgroup import TaskGroup
    from softfab.taskrunlib import TaskRun, TaskRunDB
else:
    Framework = object
    FrameworkDB = object
    ProductDef = object
    Resource = object
    TaskRunner = object
    ResultCode = object
    TaskDef = object
    TaskDefDB = object
    TaskGroup = object
    TaskRun = object
    TaskRunDB = object


class Task(
        PriorityMixin, ResourceRequirementsMixin, TaskStateMixin,
        XMLTag, TaskRunnerSet
        ):
    tagName = 'task'
    intProperties = ('priority', )

    @staticmethod
    def addTask(job: 'Job',
                name: str,
                priority: int,
                runners: Iterable[str],
                jobFactory: 'JobFactory'
                ) -> 'Task':
        tdKey = jobFactory.taskDefDB.latestVersion(name)
        assert tdKey is not None
        taskDef = jobFactory.taskDefDB.getVersion(tdKey)
        frameworkId = taskDef.frameworkId
        assert frameworkId is not None
        fdKey = jobFactory.frameworkDB.latestVersion(frameworkId)
        assert fdKey is not None
        framework = jobFactory.frameworkDB.getVersion(fdKey)

        properties: Mapping[str, XMLAttributeValue] = dict(
            name = name,
            priority = priority,
            tdKey = tdKey,
            fdKey = fdKey,
            )
        task = Task(properties, job, taskDef, framework)
        # pylint: disable=protected-access
        task._setRunners(runners)
        taskRun = jobFactory.taskRunDB.addRun(task)
        task._properties['run'] = taskRun.getId()
        task.__taskRun = taskRun
        return task

    def __init__(self,
                 attributes: Mapping[str, XMLAttributeValue],
                 job: 'Job', taskDef: TaskDef, framework: Framework
                 ):
        super().__init__(attributes)
        self._properties.setdefault('priority', 0)
        self._parameters: Dict[str, str] = {}
        self.__taskRun: Optional[TaskRun] = None
        self.__job = job
        self.__taskDef = taskDef
        self.__framework = framework

        # COMPAT 2.x.x: Remove invalid time stamps cancelled tasks.
        if self._properties.get('starttime') == 0:
            del self._properties['starttime']

    def __getitem__(self, key: str) -> object:
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

    def _addParam(self, attributes: Mapping[str, str]) -> None:
        self.addParameter(attributes['name'], attributes['value'])

    def addParameter(self, key: str, value: str) -> None:
        # Only store non-default values.
        framework = self.getFramework()
        getParent = lambda key: framework
        if self.getDef().getParameter(key, getParent) != value:
            self._parameters[key] = value

    def initCached(self, resultOnly: bool) -> None:
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
                value = cast(Union[None, str, int], taskRun[key])
                if value is not None:
                    self._properties[key] = value
        result = taskRun['result']
        if result is not None:
            self._properties['result'] = cast(ResultCode, result)
        self.__job._notify() # pylint: disable=protected-access

    def getJob(self) -> 'Job':
        return self.__job

    def getTarget(self) -> Optional[str]:
        return self.__job.getTarget()

    def getLatestRun(self) -> TaskRun:
        # Note: Because of caching __taskRun there is a reference loop, which
        #       has to be broken if the objects are to be removed from memory.
        taskRun = self.__taskRun
        if taskRun is None:
            runId = cast(str, self._properties['run'])
            taskRun = self.__job._getRun(runId) # pylint: disable=protected-access
            self.__taskRun = taskRun
        return taskRun

    def getRun(self, runId: str) -> TaskRun:
        # This is a temporary implementation until we add support for multiple
        # runs of the same task.
        if runId == '0':
            return self.getLatestRun()
        else:
            raise KeyError(runId)

    def getDef(self) -> TaskDef:
        return self.__taskDef

    def getFramework(self) -> Framework:
        return self.__framework

    def getName(self) -> str:
        return cast(str, self._properties['name'])

    def getPriority(self) -> int:
        return cast(int, self._properties['priority'])

    def _getContent(self) -> XMLContent:
        for name, value in self._parameters.items():
            yield xml.param(name = name, value = value)
        yield self.runnersAsXML()

    def getInputs(self) -> AbstractSet[str]:
        return self.getFramework().getInputs()

    def getOutputs(self) -> AbstractSet[str]:
        return self.getFramework().getOutputs()

    def getDependencies(self) -> Sequence[Product]:
        # TODO: Different terminology: input/dependency and output/produced.
        return [ self.__job.getProduct(inp) for inp in self.getInputs() ]

    def getParameter(self, name: str) -> Optional[str]:
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

    def isFinal(self, name: str) -> bool:
        '''Returns True iff the given parameter is final.
        '''
        framework = self.getFramework()
        getParent = lambda key: framework
        return self.getDef().isFinal(name, getParent)

    def getParameters(self) -> Mapping[str, str]:
        '''Returns the parameters of this task.
        '''
        framework = self.getFramework()
        getParent = lambda key: framework
        parameters = self.getDef().getParameters(getParent)
        parameters.update(self._parameters)
        return parameters

    def getVisibleParameters(self) -> Mapping[str, str]:
        '''Returns the parameters to be shown to the user:
        final and reserved parameters are not included.
        '''
        taskDef = self.getDef()
        framework = self.getFramework()
        getParent = lambda key: framework
        parameters = taskDef.getParameters(getParent)
        parameters.update(self._parameters)
        return {
            key: value
            for key, value in parameters.items()
            if not key.startswith('sf.') and not taskDef.isFinal(key, getParent)
            }

    def getNeededCaps(self) -> AbstractSet[str]:
        caps = super().getNeededCaps()
        target = self.__job.getTarget()
        if target is not None:
            caps |= {target}
        return caps

    def canRunOn(self, runner: str) -> bool:
        if self._runners:
            return runner in self._runners
        else:
            return self.__job.canRunOn(runner)

    def _getState(self) -> str:
        return cast(str, self['state'])

    @property
    def result(self) -> Optional[ResultCode]:
        return cast(Optional[ResultCode], self._properties.get('result')) \
            or self.getLatestRun().result

    @property
    def startTime(self) -> Optional[int]:
        return cast(Optional[int], self._properties.get('starttime'))

    @property
    def stopTime(self) -> Optional[int]:
        return cast(Optional[int], self._properties.get('stoptime'))

    def getDuration(self) -> Optional[int]:
        startTime = self.startTime
        stopTime = self.stopTime
        if startTime is not None and stopTime is not None:
            return stopTime - startTime
        else:
            return self.getLatestRun().getDuration()

    # The following methods forward calls to the last (currently the only)
    # TaskRun. This may not be appropriate when having multiple task runs.
    # Thus run ID should be passed as a parameter where appropriate.

    def getProduced(self) -> List[Product]:
        return self.getLatestRun().getProduced()

    def assign(self, taskRunner: TaskRunner) -> Optional[TaskRun]:
        taskRun = self.getLatestRun()
        if not taskRun.isWaiting():
            return None

        if not all(product.isAvailable() for product in self.getDependencies()):
            return None

        neededCaps = self.getNeededCaps()
        runners = self.getRunners() or self.__job.getRunners()
        if runners and taskRunner.getId() not in runners:
            return None
        elif not neededCaps <= taskRunner.capabilities:
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
            candidates: Sequence[TaskRunner] = [
                runner for runner in taskRunners
                if runner.getId() in runners
                ]
            if not candidates:
                whyNot.append(TRStateReason(StatusLevel.MISSING))
        else:
            candidates = taskRunners
        checkRunners(candidates, neededCaps, whyNot)

        taskRun.checkResources(whyNot)

    def canBeAborted(self) -> bool:
        """Returns True iff this task is in a state in which it can be
        aborted.
        """
        if self.hasResult():
            # The task has already completed.
            # Note that we check whether there is a result rather than
            # whether execution is finished, since it should be possible
            # to cancel postponed inspection.
            return False
        elif self.getLatestRun().isToBeAborted():
            # Already marked to be aborted.
            return False
        else:
            return True

    def abort(self, user: Optional[str] = None) -> Tuple[bool, str]:
        return self.getLatestRun().abort(user)

    def done(self,
             result: Optional[ResultCode],
             summary: Optional[str],
             reports: Iterable[str],
             outputs: Mapping[str, str]
             ) -> None:
        self.getLatestRun().done(result, summary, reports, outputs)

    def inspectDone(self, result: ResultCode, summary: Optional[str]) -> None:
        self.getLatestRun().inspectDone(result, summary)

    def cancelled(self, summary: str) -> None:
        self.getLatestRun().cancelled(summary)

    def getURL(self) -> Optional[str]:
        return self.getLatestRun().getURL()

    def getRunId(self) -> str:
        return self.getLatestRun().getRunId()

    def setAlert(self, alert: str) -> None:
        self.getLatestRun().setAlert(alert)

    def getAlert(self) -> Optional[str]:
        return self.getLatestRun().getAlert()

class Job(XMLTag, TaskRunnerSet, TaskSet[Task], DatabaseElem):
    '''A collection of tasks and their input and output products.
    Contains information about what should be executed,
    what has been executed and what the result was.
    '''
    tagName = 'job'
    intProperties = ('timestamp', )

    def __init__(self,
                 properties: Mapping[str, XMLAttributeValue],
                 jobFactory: 'JobFactory'
                 ):
        # Note: if the "comment" tag is empty, the XML parser does not call the
        #       <text> handler, so we have to use '' rather than None here.
        super().__init__(properties)
        self.__jobFactory = jobFactory
        self.__comment = ''
        self.__inputSet: Optional[AbstractSet[str]] = None
        self.__products: Dict[str, str] = {}
        self._params: Dict[str, str] = {}
        self.__mainGroup: Optional[TaskGroup] = None
        self.__description: Optional[str] = None
        self.__result: Optional[ResultCode] = None
        self.__leadTime: Optional[int] = None
        self.__stopTime: Optional[int] = None
        self.__executionFinished = False
        self.__resultFinal = False
        self.__inputs: Optional[Sequence[Product]] = None
        self.__produced: Optional[List[Product]] = None
        self.__notifyFlag: Optional[bool] = None
        self.__taskSequence: List[str] = []
        # __resources: { ref: [set(tasks), set(caps), id], ... }
        self.__resources: DefaultDict[str, List] = defaultdict(
            lambda: [ set(), set(), None ]
            )

        # Create a sort key which places the most recent jobs first.
        self.__recent = int(''.join(
            '%1X' % (15 - int(char, 16))
            for char in self.getId()
            if char != '-'
            ), 16)

    def __str__(self) -> str:
        return 'job[' + self.getId() + ']'

    def __getitem__(self, key: str) -> object:
        if key == 'recent':
            return self.__recent
        elif key == 'leadtime':
            return self.getLeadTime()
        elif key == 'description':
            return self.getDescription()
        elif key == 'target':
            return self.getTarget()
        elif key == 'owner':
            return self.owner
        elif key == 'scheduledby':
            return self.getScheduledBy()
        elif key == 'configId':
            return self.configId
        else:
            return XMLTag.__getitem__(self, key)

    def __addTask(self, task: Task) -> Task:
        name = task.getName()
        self._tasks[name] = task
        self.__taskSequence.append(name)
        # Examine task resource requirements
        resTypeDB = self.__jobFactory.resTypeDB
        for spec in task.resourceClaim:
            typeObj = resTypeDB.get(spec.typeName)
            if typeObj is not None and typeObj.jobExclusive:
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
                # pylint: disable=protected-access
                taskState = task._properties.get('state')
                if taskState is None or not task.isExecutionFinished():
                    tasks.add(name)
                caps.update(spec.capabilities)
        return task

    def __lockNotify(self) -> None:
        assert self.__notifyFlag is None
        self.__notifyFlag = False

    def __unlockNotify(self) -> None:
        if self.__notifyFlag:
            DatabaseElem._notify(self)
        self.__notifyFlag = None

    def _notify(self) -> None:
        if self.__notifyFlag is None:
            DatabaseElem._notify(self)
        else:
            self.__notifyFlag = True

    def _textComment(self, text: str) -> None:
        self.__comment = text

    def _addTask(self, attributes: Mapping[str, str]) -> Task:
        jobFactory = self.__jobFactory
        taskDef = jobFactory.taskDefDB.getVersion(attributes['tdKey'])
        framework = jobFactory.frameworkDB.getVersion(attributes['fdKey'])
        return self.__addTask(Task(attributes, self, taskDef, framework))

    def _addProduct(self, attributes: Mapping[str, str]) -> None:
        self.__products[attributes['name']] = attributes['key']

    def _addResource(self, attributes: Mapping[str, str]) -> None:
        self.__resources[attributes['ref']][2] = attributes.get('id') or None

    def getId(self) -> str:
        return cast(str, self._properties['jobId'])

    def __checkProduct(self, name: str) -> None:
        if not name in self.__products:
            productDB = self.__jobFactory.productDB
            self.__products[name] = productDB.create(name).getId()

    def _addParam(self, attributes: Mapping[str, str]) -> None:
        self._params[attributes['name']] = attributes['value']

    def _newTask(self, name: str, prio: int, runners: Iterable[str]) -> Task:
        '''Adds a run of the task by the given name to this job.
        Also adds all input and output products of that task, in state
        "waiting".
        This method is only intended for Config.createJobs(), which should
        add the tasks in the right order.
        '''

        task = Task.addTask(job=self, name=name, priority=prio, runners=runners,
                            jobFactory=self.__jobFactory)
        self.__addTask(task)

        productNames = task.getInputs() | task.getOutputs()
        for productName in productNames:
            self.__checkProduct(productName)
        return task

    def _getRun(self, runId: str) -> TaskRun:
        """Return the task run with the given ID.
        This method is only intended for the Task class to get access to
        the taskRunDB instance.
        """
        return self.__jobFactory.taskRunDB[runId]

    @property
    def comment(self) -> str:
        """User-specified comment string for this job.
        Comment string may contain newlines.
        Setting the comment will strip leading and trailing whitespace.
        """
        return self.__comment

    @comment.setter
    def comment(self, comment: str) -> None:
        self.__comment = comment.strip()

    def getParams(self) -> Mapping[str, str]:
        return self._params

    def getTarget(self) -> Optional[str]:
        '''Gets the target of this job.
        '''
        return cast(Optional[str], self._properties.get('target'))

    @property
    def owner(self) -> Optional[str]:
        """The owner of this job, or None if it does not have an owner."""
        return cast(Optional[str], self._properties.get('owner'))

    def getScheduledBy(self) -> Optional[str]:
        """Gets the ID of the schedule that started of this job,
        or None if this job was not started from a schedule.
        """
        return cast(Optional[str], self._properties.get('scheduledby'))

    def setScheduledBy(self, scheduleId: str) -> None:
        """Store the ID of the schedule that started this job.
        """
        self._properties['scheduledby'] = scheduleId

    def _isProductFixed(self, product: Product) -> bool:
        '''Returns True iff all tasks that produce the given product are fixed.
        Used to determine when a combined product is available, or when to
        give up on a non-combined product.
        '''
        return all(
            task.isExecutionFinished()
            for task in self.getProducers(product.getName())
            )

    def _blockProduct(self, product: Product) -> None:
        product.blocked()
        productName = product.getName()
        for task in self.getConsumers(productName):
            if task.isWaiting():
                task.cancelled(productName + ' is not available')

    def _getContent(self) -> XMLContent:
        if self.__comment:
            yield xml.comment[ self.__comment ]
        for key, value in self._params.items():
            yield xml.param(name = key, value = value)
        for task in self.__taskSequence:
            yield self._tasks[task]
        for name, key in self.__products.items():
            yield xml.product(name = name, key = key)
        yield self.runnersAsXML()
        for ref, (_, _, resId) in self.__resources.items():
            yield xml.resource(ref = ref, id = resId)

    def isCompleted(self) -> bool:
        '''Returns True iff all tasks in this job have run and have a result.
        '''
        return all(
            task.isDone() and task.hasResult()
            for task in self._tasks.values()
            )

    def isExecutionFinished(self) -> bool:
        '''Returns True iff execution of all tasks in this job is finished.
        Note that a job that has finished execution might not have its result
        available yet if it is waiting for inspection.
        '''
        if not self.__executionFinished:
            self.__executionFinished = all(
                task.isExecutionFinished()
                for task in self._tasks.values()
                )
        return self.__executionFinished

    def hasFinalResult(self) -> bool:
        '''Returns True iff the final result of this job is available.
        '''
        if not self.__resultFinal:
            self.__resultFinal = all(
                task.hasResult()
                for task in self._tasks.values()
                )
        return self.__resultFinal

    def _getMainGroup(self) -> TaskGroup:
        mainGroup = self.__mainGroup
        if mainGroup is None:
            mainGroup = super()._getMainGroup()
            self.__mainGroup = mainGroup
        return mainGroup

    def getTaskSequence(self) -> Sequence[Task]:
        return [ self._tasks[task] for task in self.__taskSequence ]

    def iterTasks(self) -> Iterator[Task]:
        '''Yields the tasks in this job, in arbitrary order.
        '''
        return iter(self._tasks.values())

    @property
    def configId(self) -> Optional[str]:
        """The ID of the configuration this job was once created from,
        or None if this job was created from scratch.
        """
        return cast(Optional[str], self._properties.get('configId'))

    def getDescription(self) -> str:
        # Since task definition is fixed, caching is possible.
        description = self.__description
        if description is None:
            description = self.configId or super().getDescription()
            self.__description = description
        return description

    def canRunOn(self, runner: str) -> bool:
        if self._runners:
            return runner in self._runners
        else:
            return True

    def getFinalResult(self) -> Optional[ResultCode]:
        '''Returns the ResultCode of the final result of this job, or None if
        this job does not have a final result yet.
        '''
        return self.result if self.hasFinalResult() else None

    @property
    def result(self) -> Optional[ResultCode]:
        '''Summarizes the current result of this job by combining the task
        results into a single value.
        The result returned by this method applies to the current situation
        and might change in the future; if that is not what you want, use
        getFinalResult() instead.
        '''
        if self.__result is not None:
            return self.__result
        result = max((task.result for task in self._tasks.values()),
                     default=None)
        if self.hasFinalResult():
            self.__result = result
        return result

    def getRecent(self) -> int:
        return self.__recent

    def getCreateTime(self) -> int:
        return cast(int, self._properties['timestamp'])

    def getLeadTime(self) -> int:
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
        stopTime = self.stopTime
        if stopTime is None:
            return getTime() - queueTime
        else:
            leadTime = stopTime - queueTime
            self.__leadTime = leadTime
            return leadTime

    @property
    def stopTime(self) -> Optional[int]:
        """This job's stop time, or None if it has not stopped yet."""
        if self.__stopTime is None and self.isExecutionFinished():
            # Note: Execution is finished, so every task will have a stop time.
            self.__stopTime = max(
                task.stopTime for task in self._tasks.values()
                )
        return self.__stopTime

    def getInputSet(self) -> AbstractSet[str]:
        if self.__inputSet is None:
            self.__inputSet = super().getInputSet()
        return self.__inputSet

    def getInputs(self) -> Sequence[Product]:
        """Returns the input products of this job.
        """
        if self.__inputs is None:
            self.__inputs = tuple(
                self.getProduct(inputName)
                for inputName in self.getInputSet()
                )
        return self.__inputs

    def getProduced(self) -> Sequence[Product]:
        '''Returns the products produced by this job, in the most
        likely creation order.
        '''
        if self.__produced is None:
            produced: List[Product] = []
            producedNames: MutableSet[str] = set()
            for task in self.getTaskSequence():
                taskProduced = {}
                for product in task.getProduced():
                    name = product.getName()
                    if name not in producedNames:
                        taskProduced[name] = product
                for name, product in sorted(taskProduced.items()):
                    producedNames.add(name)
                    produced.append(product)
            self.__produced = produced
        return self.__produced

    def setInputLocator(self,
                        name: str,
                        locator: str,
                        taskRunnerId: Optional[str],
                        taskName: str
                        ) -> None:
        '''Mark an input as available and provide its locator.
        The taskName parameter provides a fake task name for the producer.
        Raises ValueError if `taskRunnerId` is None for a local product.
        '''
        assert name in self.getInputSet(), \
            f'{name} not in {self.getInputSet()}'
        assert locator is not None
        product = self.getProduct(name)
        localProduct = product.isLocal()
        if taskRunnerId is None and localProduct:
            raise ValueError(
                f'No Task Runner specified for local product "{name}"'
                )
        product.done()
        product.storeLocator(locator, taskName)
        if localProduct:
            assert taskRunnerId is not None
            product.setLocalAt(taskRunnerId)

    def assignTask(self, taskRunner: TaskRunner) -> Optional[TaskRun]:
        '''Tries to assign a task in this job to the given Task Runner.
        Returns the task assigned, or None if no task could be assigned.
        '''
        assigned = self._getMainGroup().assign(taskRunner)
        if assigned is not None:
            # TODO: We need real transactions, because reserved resources will
            #       never be freed if the job (later task run) is not committed.
            self._notify()
        return assigned

    def updateSummaries(self, taskRunners: Sequence[TaskRunner]) -> None:
        """Updates the summaries for the waiting tasks in this job.
        You can get the new summaries using the TaskRun.getSummary().
        """
        if not self.isExecutionFinished():
            whyNot: List[ReasonForWaiting] = []
            self._getMainGroup().checkRunners(taskRunners, whyNot)

    def taskDone(self,
                 name: str,
                 result: Optional[ResultCode],
                 summary: Optional[str],
                 reports: Iterable[str],
                 outputs: Mapping[str, str]
                 ) -> None:
        """Marks a task as done and stores the result.
        """
        if not self.isExecutionFinished():
            self.__lockNotify()
            try:
                self._tasks[name].done(result, summary, reports, outputs)
            finally:
                self.__unlockNotify()

    def inspectDone(self,
                    name: str,
                    result: ResultCode,
                    summary: Optional[str]
                    ) -> None:
        '''Stores result of a postponed inspection.
        '''
        self._tasks[name].inspectDone(result, summary)

    def abortTask(self, name: str, user: Optional[str] = None) -> str:
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

    def abortAll(self,
                 taskFilter: Callable[[Task], bool] = lambda t: True,
                 user: Optional[str] = None
                 ) -> Iterable[str]:
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

    def getProduct(self, name: str) -> Product:
        '''Returns the product with the given name.
        Raises KeyError if there is no product with the given name in this job.
        '''
        productDB = self.__jobFactory.productDB
        return productDB[self.__products[name]]

    def getProductDef(self, name: str) -> ProductDef:
        # Go through the Product object to get the correct version.
        return self.getProduct(name).getDef()

    def getProductLocation(self, name: str) -> Optional[str]:
        return self.getProduct(name).getLocalAt()

    def reserveResources(self,
                         claim: ResourceClaim,
                         reservedBy: str,
                         whyNot: Optional[List[ReasonForWaiting]]
                         ) -> Optional[Dict[str, Resource]]:
        resourceDB = self.__jobFactory.resourceDB
        if self.__resources:
            bound = {}
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
                        bound[ref] = resId
                    else:
                        keepPerJob.append(ref)
                        if caps != specCaps:
                            spec = ResourceSpec.create(ref, resType, caps)
                        toReserve.append(spec)
                else:
                    toReserve.append(spec)
            reservedPerJob = {}
            for ref, resId in bound.items():
                resource = resourceDB.get(resId)
                if resource is not None:
                    assert isinstance(resource, Resource), resId
                    reservedPerJob[ref] = resource
                else:
                    if whyNot is not None:
                        # TODO: report multiple resources at the same time
                        whyNot.append(ResourceMissingReason(resId))
                    return None
            reservedBy = 'J-' + self.getId()
            reserved = _reserveResources(resourceDB,
                                         ResourceClaim.create(toReserve),
                                         reservedBy, whyNot)
            if reserved is not None:
                for ref in keepPerJob:
                    self.__resources[ref][2] = reserved[ref].getId()
                reserved.update(reservedPerJob)
            return reserved
        else:
            return _reserveResources(resourceDB, claim, reservedBy, whyNot)

    def releaseResources(self,
                         task: Task,
                         reserved: Optional[Mapping[str, str]]
                         ) -> None:
        resourceDB = self.__jobFactory.resourceDB
        if self.__resources:
            toRelease: Dict[str, str] = dict(reserved or ())
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
                _releaseResources(resourceDB, toRelease.values())
        elif reserved is not None:
            _releaseResources(resourceDB, reserved.values())

def _reserveResources(resourceDB: ResourceDB,
                      claim: ResourceClaim,
                      reservedBy: str,
                      whyNot: Optional[List[ReasonForWaiting]] = None
                      ) -> Optional[Dict[str, Resource]]:
    # TODO: Database is not actually a Mapping.
    #       It's close enough, but I'd rather not cheat the type system.
    #       Also the element type is actually ResourceBase.
    resources = cast(Mapping[str, Resource], resourceDB)
    assignment = pickResources(claim, resources, whyNot)
    if assignment is not None and whyNot is None:
        for resource in assignment.values():
            resType = resource.resType
            if resType.jobExclusive or resType.taskExclusive:
                resource.reserve(reservedBy)
    return assignment

def _releaseResources(resourceDB: ResourceDB, reserved: Iterable[str]) -> None:
    for resId in reserved:
        resource = resourceDB.get(resId)
        if resource is not None:
            # Check that resource is a custom resource (not a Task Runner).
            assert isinstance(resource, Resource), resId
            resType = resource.resType
            if resType.jobExclusive or resType.taskExclusive:
                resource.free()

class JobFactory:

    productDB: ProductDB
    resourceDB: ResourceDB
    resTypeDB: ResTypeDB
    taskRunDB: TaskRunDB
    frameworkDB: FrameworkDB
    taskDefDB: TaskDefDB

    def createJob(self, attributes: Mapping[str, str]) -> Job:
        return Job(attributes, self)

    def newJob(self,
               configId: Optional[str],
               target: Optional[str],
               owner: Optional[str],
               comment: str,
               jobParams: Mapping[str, str],
               runners: Iterable[str]
               ) -> Job:
        # TODO: Is validation needed?
        properties: Dict[str, XMLAttributeValue] = dict(
            jobId = createUniqueId(),
            timestamp = getTime(),
            )
        if configId is not None:
            properties['configId'] = configId
        if target is not None:
            properties['target'] = target
        if owner is not None:
            properties['owner'] = owner

        job = Job(properties, self)
        job.comment = comment
        # pylint: disable=protected-access
        job._params.update(jobParams)
        job._setRunners(runners)
        return job



# Work around lack of knowledge of @property in mypy.
#   https://github.com/python/mypy/issues/7974
if TYPE_CHECKING:
    _ownerRetreiver = Job.owner
    _configIdRetriever = Job.configId
else:
    # PyLint doesn't understand @property either.
    _ownerRetreiver = Job.owner.__get__ # pylint: disable=no-member
    _configIdRetriever = Job.configId.__get__ # pylint: disable=no-member

class JobDB(Database[Job]):
    privilegeObject = 'j'
    description = 'job'
    cachedUniqueValues = ( 'owner', 'target' )
    uniqueKeys = ( 'recent', 'jobId' )

    # TODO: These casts are lies to paper over the fact that these retrievers
    #       can return None, which is not a Comparable.
    keyRetrievers = {
        'recent': Job.getRecent,
        'timestamp': Job.getCreateTime,
        'leadtime': Job.getLeadTime,
        'target': cast(Retriever[Job, Comparable], Job.getTarget),
        'description': Job.getDescription,
        'owner': cast(Retriever[Job, Comparable], _ownerRetreiver),
        'configId': cast(Retriever[Job, Comparable], _configIdRetriever),
        }

    def __init__(self, baseDir: Path):
        super().__init__(baseDir, JobFactory())

jobDB = JobDB(dbDir / 'jobs')
taskrunlib.jobDB = jobDB

class TaskToJobs(RecordObserver[Job]):
    '''For each task ID, keep track of the IDs of all jobs containing that task.
    '''
    def __init__(self, jobDB: JobDB):
        super().__init__()
        self.__taskToJobs: DefaultDict[str, List[Job]] = defaultdict(list)

        for job in jobDB:
            self.added(job)
        jobDB.addObserver(self)

    def __getitem__(self, taskName: str) -> Iterable[Job]:
        return self.__taskToJobs.get(taskName, [])

    def iterTasksWithId(self, taskName: str) -> Iterator[Task]:
        for job in self[taskName]:
            task = job.getTask(taskName)
            assert task is not None
            yield task

    def iterAllTasks(self, taskFilter: Iterable[str]) -> Iterator[Task]:
        for taskId in taskFilter:
            yield from self.iterTasksWithId(taskId)

    def iterDoneTasks(self, taskFilter: Iterable[str]) -> Iterator[Task]:
        for task in self.iterAllTasks(taskFilter):
            if task.isDone():
                yield task

    def iterFinishedTasks(self, taskFilter: Iterable[str]) -> Iterator[Task]:
        for task in self.iterAllTasks(taskFilter):
            if task.hasResult():
                yield task

    def iterUnfinishedTasks(self, taskFilter: Iterable[str]) -> Iterator[Task]:
        for task in self.iterAllTasks(taskFilter):
            if not task.hasResult():
                yield task

    def added(self, record: Job) -> None:
        taskToJobs = self.__taskToJobs
        for taskName in record.iterTaskNames():
            taskToJobs[taskName].append(record)

    def removed(self, record: Job) -> None:
        assert False, 'jobs should not be removed'

    def updated(self, record: Job) -> None:
        # We don't care, since the set of tasks will not be different.
        pass

class DateRangeMonitor(RecordObserver[Job]):
    @property
    def minTime(self) -> int:
        return self.__minTime

    @property
    def maxTime(self) -> int:
        return self.__maxTime

    @property
    def minYear(self) -> int:
        return self.__minYear

    @property
    def maxYear(self) -> int:
        return self.__maxYear

    def __init__(self, jobDB: JobDB) -> None:
        super().__init__()
        # Determine minimum and maximum job time.
        createTimes = [ job.getCreateTime() for job in jobDB ]
        if createTimes:
            self.__minTime = min(createTimes)
            self.__maxTime = max(createTimes)
        else:
            now = getTime()
            self.__minTime = now
            self.__maxTime = now
        self.__minYear = localtime(self.__minTime)[0]
        self.__maxYear = localtime(self.__maxTime)[0]

        # Register for updates.
        jobDB.addObserver(self)

    def added(self, record: Job) -> None:
        createTime = record.getCreateTime()
        self.__maxTime = createTime
        year = localtime(createTime)[0]
        if year > self.__maxYear:
            self.__maxYear = year

    def removed(self, record: Job) -> None:
        assert False, 'job was removed'

    def updated(self, record: Job) -> None:
        # Create time cannot change, so we don't care.
        pass

class UnfinishedJobs(SortedQueue[Job]):
    compareField = 'timestamp'

    def _filter(self, record: Job) -> bool:
        return not record.isExecutionFinished()

class ResultlessJobs(SortedQueue[Job]):
    compareField = 'timestamp'

    def _filter(self, record: Job) -> bool:
        return not record.hasFinalResult()

# SPDX-License-Identifier: BSD-3-Clause

from typing import (
    TYPE_CHECKING, Dict, Iterable, Iterator, List, Mapping, Optional, Tuple,
    cast
)
from urllib.parse import urljoin
import logging

from softfab import shadowlib
from softfab.config import dbDir
from softfab.conversionflags import upgradeInProgress
from softfab.databaselib import (
    Database, DatabaseElem, ObsoleteRecordError, createInternalId
)
from softfab.resreq import ResourceClaim
from softfab.restypelib import taskRunnerResourceTypeName
from softfab.resultcode import ResultCode
from softfab.storagelib import StorageURLMixin
from softfab.tasklib import TaskStateMixin
from softfab.timelib import getTime
from softfab.timeview import formatTime
from softfab.utils import IllegalStateError, cachedProperty, pluralize
from softfab.waiting import ReasonForWaiting, topWhyNot
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XML, XMLContent, xml

if TYPE_CHECKING:
    from softfab.joblib import Job, Task, jobDB
    from softfab.productlib import Product
    from softfab.resourcelib import Resource, ResourceDB, TaskRunner
    from softfab.shadowlib import ExtractionRun
    from softfab.userlib import User
else:
    Job = object
    Task = object
    # Note: To avoid cyclic imports, joblib sets this.
    #       The weird construct is to avoid PyLint complaining about methods we
    #       call on it not existing for NoneType.
    jobDB = cast(Database, (lambda x: x if x else None)(0))
    Product = object
    Resource = object
    ResourceDB = object
    TaskRunner = object
    ExtractionRun = object
    User = object


defaultSummaries = {
    ResultCode.OK: 'executed successfully',
    ResultCode.WARNING: 'executed with warnings',
    ResultCode.ERROR: 'execution failed',
    ResultCode.INSPECT: None,
    }

class TaskRun(XMLTag, DatabaseElem, TaskStateMixin, StorageURLMixin):
    tagName = 'taskRun'
    intProperties = ('runId', )

    def __init__(self,
                 attributes: Mapping[str, str],
                 task: Optional[Task] = None
                 ):
        XMLTag.__init__(self, attributes)
        DatabaseElem.__init__(self)
        TaskStateMixin.__init__(self)
        self.__task = task
        if task is None:
            self.__job = None # type: Optional[Job]
        else:
            self.__job = task.getJob()
        # This will be set during XML parsing.
        self.__jobId = cast(str, None)
        if 'state' not in self._properties:
            # Initial state.
            self._properties['state'] = 'waiting'
        self.__reports = [] # type: List[str]
        self.__reserved = {} # type: Dict[str, str]
        self.__reasonForWaiting = None # type: Optional[ReasonForWaiting]

        self._properties.setdefault('runId', 0)
        # 'abort' is either 'true' or doesn't exist
        if 'abort' in self._properties and \
        (self._properties['state'] != 'running' or \
        self._properties['abort'] != 'true'):
            del self._properties['abort']
        if 'alert' in self._properties and \
        self._properties['state'] != 'running':
            del self._properties['alert']

        self.__extractionRun = None # type: Optional[ExtractionRun]
        if 'extractionRun' in self._properties:
            extractionRunId = cast(str, self._properties['extractionRun'])
            extractionRun = shadowlib.shadowDB.get(extractionRunId)
            # There is currently only one type of shadow run.
            assert isinstance(extractionRun, ExtractionRun), extractionRun
            self.__setExtractionRun(extractionRun)
            # Even if the extraction run has been deleted already, keep the ID
            # around as a marker that this run was once extracted.
            # ShowReports uses this to decide whether or not to show the
            # "view data" link.
        StorageURLMixin.__init__(self)

    def __getitem__(self, key: str) -> object:
        if key == 'state':
            return self._getState()
        elif key == 'result':
            return self.getResult()
        elif key == 'duration':
            return self.getDuration()
        elif key == 'starttime':
            return self.getStartTime()
        elif key == '-starttime':
            startTime = self.getStartTime()
            return None if startTime is None else -startTime
        elif key == 'stoptime':
            return self.getStopTime()
        elif key == 'summary':
            return self.getSummary()
        elif key in ( 'runner', 'extractionRun' ):
            # It is perfectly legal for these keys not to exist.
            return self._properties.get(key)
        else:
            value = self._properties.get(key)
            if value is None:
                return self.getJob()[key]
            else:
                return value

    def __setExtractionRun(self, extractionRun: ExtractionRun) -> None:
        if self.__extractionRun is not None:
            self.__extractionRun.removeObserver(self.__extractionRunChanged)
        self.__extractionRun = extractionRun
        if extractionRun is not None and not extractionRun.isDone():
            extractionRun.addObserver(self.__extractionRunChanged)

    def __extractionRunChanged(self, extractionRun: ExtractionRun) -> None:
        if extractionRun.isDone():
            if 'result' not in self._properties:
                # Extraction is finished and we still don't have a result.
                self.__setState(ResultCode.ERROR, 'done',
                    'neither wrapper nor extractor specified result'
                    )
                self._notify()
            # No further updates will come, so no point in listening.
            extractionRun.removeObserver(self.__extractionRunChanged)

    def __getJobId(self) -> str:
        if self.__job is None:
            # During upgrade, job ID is stored because job is not.
            return self.__jobId
        else:
            return self.__job.getId()

    def _addReport(self, attributes: Mapping[str, str]) -> None:
        self.__reports.append(attributes['name'])

    def _addResource(self, attributes: Mapping[str, str]) -> None:
        self.__reserved[attributes['ref']] = attributes['id']

    def _setTask(self, attributes: Mapping[str, str]) -> None:
        if upgradeInProgress:
            if attributes['job'] not in jobDB:
                raise ObsoleteRecordError()
            self.__jobId = attributes['job'] # pylint: disable=attribute-defined-outside-init
            self.__taskName = attributes['name'] # pylint: disable=attribute-defined-outside-init
        else:
            # TODO: The delayed initialization is required when loading a job
            #       with non-finished tasks.
            self.__jobId = attributes['job'] # pylint: disable=attribute-defined-outside-init
            self.__taskName = attributes['name'] # pylint: disable=attribute-defined-outside-init
            #self.__job = jobDB[attributes['job']]
            #self.__task = self.__job.getTask(attributes['name'])

    def createRunXML(self) -> XML:
        return xml.run(
            jobId = self.__getJobId(),
            taskId = self.getName(),
            runId = self.getRunId()
            )

    def createTaskXML(self) -> XML:
        task = self.getTask()
        return xml.task(
            target = self.getJob().getTarget() or '',
            # COMPAT 2.x.x: The TR doesn't use this value anymore, but if we
            #               omit it, the XML unpacking will fail.
            framework = 'for backwards compatibility only',
            script = task.getParameter('script') or ''
            )[(
                xml.param(name = name, value = value)
                for name, value in task.getParameters().items()
            )]

    def createInputXML(self) -> XMLContent:
        for inp in self.getTask().getDependencies():
            yield xml.input(
                name = inp.getName(),
                # For combined products, it is possible that none of the
                # potential producers have actually produced the product,
                # therefore the locator can be None. However, the Task Runner
                # requires a locator to be passed or it will fail to parse
                # the command it receives. See ticket #283.
                locator = inp.getLocator() or ''
                )[self.createProducerXML(inp)]

    def createOutputXML(self) -> XMLContent:
        for outputName in self.getTask().getOutputs():
            yield xml.output(name = outputName)

    def createProducerXML(self, product: Product) -> XMLContent:
        job = self.getJob()
        # Provide an empty locator for every task that has the given
        # product as an output.
        locators = dict.fromkeys(
            ( task.getName()
                for task in job.getProducers(product.getName()) ),
            ''
            )
        # Replace the empty locators by the actual locators, for those
        # tasks that stored a locator.
        locators.update(product.getProducers())
        # Create XML.
        for taskName, locator in locators.items():
            task = job.getTask(taskName)
            if task is not None:
                # If a task can produce this product, get the result from
                # the task.
                result = task.getResult()
            else:
                # No task produced this product, so it's a user input.
                result = ResultCode.OK
            # It is possible for the result to be None if for example
            # the task didn't finish yet or is awaiting extraction.
            # The parser in the Task Runner will not accept a producer
            # without a result though, so use "notyet" instead.
            yield xml.producer(
                taskId=taskName,
                locator=locator,
                result=result or 'notyet'
                )

    def getId(self) -> str:
        return cast(str, self._properties['id'])

    def getTask(self) -> Task:
        task = self.__task
        if task is None:
            # During upgrade, task name is stored because task is not.
            # However, in special cases a particular job is needed, so load it.
            self.__task = task = self.getJob().getTask(self.__taskName)
            assert task is not None
        return task

    def getName(self) -> str:
        if self.__task is None:
            # During upgrade, task name is stored because task is not.
            return self.__taskName
        else:
            return self.__task.getName()

    def _getContent(self) -> XMLContent:
        for report in self.__reports:
            yield xml.report(name = report)
        for ref, resId in self.__reserved.items():
            yield xml.resource(ref = ref, id = resId)
        yield xml.task(name = self.getName(), job = self.__getJobId())

    # TODO: Should this remain public?
    #       It is used by ExtractedData at least, but will it stay that way?
    def getJob(self) -> Job:
        job = self.__job
        if job is None:
            # During upgrade, job ID is stored because job is not.
            # However, in special cases a particular job is needed, so load it.
            self.__job = job = jobDB[self.__jobId]
        return job

    def _getState(self) -> str:
        return cast(str, self._properties['state'])

    def getAlert(self) -> Optional[str]:
        return cast(Optional[str], self._properties.get('alert'))

    def getRunId(self) -> str:
        return str(self._properties['runId'])

    def getTaskRunnerId(self) -> Optional[str]:
        '''Returns the ID of the Task Runner that is currently executing this
        task run or has executed it.
        If execution has not yet started, None is returned.
        '''
        return cast(Optional[str], self._properties.get('runner'))

    def getSummary(self) -> str:
        if self.isRunning():
            if 'abort' in self._properties:
                return 'abort in progress'
            else:
                return 'execution in progress'
        # When aborting a running task, the "who aborted" text is stored
        # as the summary, but should not be displayed until the task has
        # actually stopped executing.
        storedSummary = cast(Optional[str], self._properties.get('summary'))
        if storedSummary is not None:
            return storedSummary
        elif self.isWaiting():
            reasonForWaiting = self.__reasonForWaiting
            if reasonForWaiting is None:
                return 'waiting for execution'
            else:
                return reasonForWaiting.description
        else:
            result = self.getResult()
            if result is ResultCode.INSPECT:
                return 'waiting for postponed inspection'
            elif result is None:
                if self.__extractionRun is not None \
                and self.__extractionRun.isRunning():
                    return 'extraction in progress'
                else:
                    return 'waiting for extraction'
            elif result in defaultSummaries:
                summary = defaultSummaries[result]
                assert summary is not None
                return summary
            else:
                return 'no summary available'

    @property
    def reports(self) -> Iterator[Tuple[str, str]]:
        """The reports that currently exist for this task.
        Each report is a pair consisting of file name and full URL.
        """
        url = self.getURL()
        if url is not None:
            reports = list(self.__reports)
            if not reports:
                # COMPAT: Backwards compatibility with reports on Factory PC.
                summary = self.getTask().getParameter('sf.summary')
                if summary:
                    reports.append(summary)
                reports.append('wrapper_log.txt')
            for report in reports:
                yield report.rstrip('/'), urljoin(url, report)

    @cachedProperty
    def timeoutMins(self) -> Optional[int]:
        '''Task execution timeout in minutes, or None for never.
        The timeout is stored in the special property "sf.timeout".
        '''
        timeout = self.getTask().getParameter('sf.timeout')
        return None if timeout is None else int(timeout)

    def isTimedOut(self) -> bool:
        """Returns True if the task timed out according to the setting of
        Time Out in the Task Definition
        """
        timeoutMins = self.timeoutMins
        if timeoutMins is None:
            # Never timeout.
            return False
        else:
            duration = self.getDuration()
            if duration is None:
                # Not started yet.
                return False
            else:
                return duration >= timeoutMins * 60

    def isToBeAborted(self) -> bool:
        """Returns True if the task timed out or when the user aborted the
        task or when the execution of the task is finished
        """
        tobeAborted = self.isTimedOut() or 'abort' in self._properties \
            or self.isExecutionFinished()
        return tobeAborted

    def getProduced(self) -> List[Product]:
        """Gets list of all products that can be produced by this task.
        This is a static property of this task.
        """
        return [
            self.getJob().getProduct(output)
            for output in self.getTask().getOutputs()
            ]

    def getStartTime(self) -> Optional[int]:
        return cast(Optional[int], self._properties.get('starttime'))

    def getStopTime(self) -> Optional[int]:
        return cast(Optional[int], self._properties.get('stoptime'))

    def getDuration(self) -> Optional[int]:
        startTime = self.getStartTime()
        if startTime is None:
            return None
        stopTime = self.getStopTime()
        if stopTime is None:
            return getTime() - startTime
        return stopTime - startTime

    def assign(self, taskRunner: TaskRunner) -> Optional['TaskRun']:
        assert self.isWaiting()

        resources = self.__reserveResources(None)
        if resources is None:
            return None

        self.__reserved = {ref: res.getId() for ref, res in resources.items()}
        self._properties['state'] = 'running'
        self._properties['starttime'] = getTime()
        self._properties['runner'] = taskRunner.getId()
        #self._properties['runId'] += 1
        self._notify()
        return self

    def checkResources(self, whyNot: List[ReasonForWaiting]) -> None:
        assert self.isWaiting()
        self.__reserveResources(whyNot)
        self.__reasonForWaiting = topWhyNot(whyNot) if whyNot else None

    def __reserveResources(self,
                           whyNot: Optional[List[ReasonForWaiting]]
                           ) -> Optional[Mapping[str, Resource]]:
        # TODO: Treat Task Runners the same as other resources.
        nonTRClaim = ResourceClaim.create(
            spec
            for spec in self.getTask().resourceClaim
            if spec.typeName != taskRunnerResourceTypeName
            )

        # Try to reserve the necessary resources.
        return self.getJob().reserveResources(
            nonTRClaim, 'T-' + self.getId(), whyNot
            )

    def abort(self, user: Optional[str] = None) -> Tuple[bool, str]:
        '''Attempts to abort this task.
        Returns a pair of a boolean and a message string.
        The boolean is True if this task was cancelled or marked for abortion
        and False if this task cannot be aborted.
        '''
        whoAborted = ' by user%s at %s' % (
            '' if user is None else f' "{user}"', formatTime(getTime())
            )
        if self.isRunning():
            if 'abort' in self._properties:
                return False, 'was already being aborted'
            else:
                self._properties['abort'] = 'true'
                self._properties['summary'] = 'aborted' + whoAborted
                self._notify()
                return True, 'will be aborted shortly'
        elif self.isWaiting():
            self.cancelled('cancelled' + whoAborted)
            return True, 'has been aborted'
        elif self.isWaitingForInspection():
            self.__setState(
                ResultCode.ERROR, 'done',
                'postponed inspection cancelled' + whoAborted
                )
            return True, 'had its postponed inspection cancelled'
        elif self.isDone() and self.getResult() is None:
            return False, 'cannot be aborted: ' \
                'aborting extraction is not yet implemented'
        else:
            return False, 'was not waiting or running'

    def setAlert(self, alert: str) -> None:
        if alert and self.isRunning():
            self._properties['alert'] = alert
            self._notify()
        elif 'alert' in self._properties:
            del self._properties['alert']
            self._notify()

    def __setState(self,
                   result: Optional[ResultCode],
                   newState: str,
                   summary: Optional[str],
                   outputs: Optional[Mapping[str, str]] = None
                   ) -> None:
        if result is not None and not isinstance(result, ResultCode):
            raise TypeError('result must be a ResultCode or None')

        products = self.getProduced()

        # Check if non-existing output.PRODUCT.locators are set.
        if outputs:
            filteredOutputs = dict(outputs)
            unknownProducts = [
                outputName
                for outputName in outputs.keys()
                if all(outputName != product.getName() for product in products)
                ]
            if unknownProducts:
                # Remove locators for non-existing products.
                for productName in unknownProducts:
                    del filteredOutputs[productName]
                # Overrule result and summary.
                result = ResultCode.WARNING
                summary = \
                    'Wrapper sets output locator for non-existing %s: %s' % (
                        pluralize('product', unknownProducts),
                        ', '.join(sorted(unknownProducts))
                        )
        else:
            filteredOutputs = {}

        if result is not None:
            self._properties['result'] = result
        if summary is not None:
            self._properties['summary'] = summary
        self._properties['state'] = newState
        self._properties['stoptime'] = getTime()
        if 'abort' in self._properties:
            del self._properties['abort']
        if 'alert' in self._properties:
            del self._properties['alert']

        # Update state of outputs.
        for product in products:
            # Store locator.
            locator = filteredOutputs.get(product.getName())
            if locator is not None:
                product.storeLocator(locator, self.getName())
            # Is the product done now?
            if product.isCombined():
                if self.getJob()._isProductFixed(product):
                    product.done()
            else:
                # Locator availability determines whether product is available
                # or not. This new behaviour was introduced in SoftFab 2.10.0,
                # along with local products.
                if locator is None:
                    if self.getJob()._isProductFixed(product):
                        self.getJob()._blockProduct(product)
                else:
                    product.done()

        # Trigger property cache for task objects in joblib.
        if self.hasResult():
            self.getTask().initCached(resultOnly = False)

    def done(self,
             result: Optional[ResultCode],
             summary: Optional[str],
             reports: Iterable[str],
             outputs: Mapping[str, str]
             ) -> None:
        task = self.getTask()

        # Input validation.
        # It is important this occurs before the database is modified:
        # all changes should be applied or none of them.
        if isinstance(result, ResultCode):
            if result not in defaultSummaries:
                raise ValueError(result)
        elif result is not None:
            raise TypeError('result must be a ResultCode or None')
        if self.isExecutionFinished():
            return
        assert self.isRunning()
        if result is None and not task.hasExtractionWrapper():
            result = ResultCode.ERROR
            summary = 'wrapper did not specify result'
        if 'abort' in self._properties:
            # Keep the "who aborted" message, since it is more informative
            # than what the Task Runner sends.
            summary = None
            # Make sure result and summary are consistent.
            result = ResultCode.ERROR

        self.__setState(result, 'done', summary, outputs)

        # Remember reports.
        artifactsPaths = self.__getJobId().split('-', 1)
        artifactsPaths += (self.getName(), '')
        self.setInternalStorage('/'.join(artifactsPaths))
        self.__reports += reports

        # TODO: Mark as freed, but remember which resources were used.
        #       Maybe do this when we start modeling Task Runners as resources.
        self.getJob().releaseResources(task, self.__reserved)
        self.__reserved = {}

        if self.getTask().hasExtractionWrapper() \
                and result is not ResultCode.ERROR:
            # Create extraction shadow run.
            extractionRun = shadowlib.ExtractionRun.create(self)
            shadowlib.shadowDB.add(extractionRun)
            # Remember which extraction run belongs to this task run.
            self._properties['extractionRun'] = extractionRun.getId()
            self.__setExtractionRun(extractionRun)

        self._notify()

    def inspectDone(self, result: ResultCode, summary: Optional[str]) -> None:
        # Input validation.
        if result not in (
            ResultCode.OK, ResultCode.WARNING, ResultCode.ERROR
            ):
            raise ValueError(result)
        if not self.isWaitingForInspection():
            raise IllegalStateError(
                f'task "{self.getId()}" received unexpected inspection result'
                )

        self._properties['result'] = result
        if summary is not None:
            self._properties['summary'] = summary

        self._notify()
        # Trigger property cache for task objects in joblib
        self.getTask().initCached(resultOnly = True)

    def cancelled(self, summary: str) -> None:
        assert self.isWaiting()
        self.__setState(ResultCode.CANCELLED, 'cancelled', summary)
        self.getJob().releaseResources(self.getTask(), None)
        self._notify()

    def failed(self, message: str) -> None:
        '''Marks this run as failed.
        Used when a Task Runner is not behaving like it should, for example
        the Task Runner is lost.
        '''
        self.getJob().taskDone(
            self.getName(), ResultCode.ERROR, message, (), {}
            )

    def setResult(self,
                  result: Optional[ResultCode],
                  summary: Optional[str]
                  ) -> None:
        if isinstance(result, ResultCode):
            if result not in defaultSummaries:
                raise ValueError(result)
        elif result is not None:
            raise TypeError('result must be a ResultCode or None')
        if not self.isExecutionFinished():
            raise IllegalStateError('only finished tasks can have results')

        oldResult = self.getResult()
        if oldResult is None or oldResult is result:
            # Compatible result.
            if oldResult is None and result is not None:
                self._properties['result'] = result
                self.getTask().initCached(resultOnly = True)
            if summary is not None:
                self._properties['summary'] = summary
        else:
            # Conflicting result.
            logging.warning(
                'ignoring conflicting new result %s (summary "%s") '
                'for run %s of task %s of job %s with old result %s',
                result, summary,
                self.getRunId(), self.getName(), self.__getJobId(), oldResult
                )
        self._notify()

    def externalize(self, resourceDB: ResourceDB) -> XML:
        '''Returns an XMLNode which contains the information which
        the Task Runner needs to perform this execution run.
        '''
        return xml.start[
            self.createRunXML(),
            self.createTaskXML(),
            self.createInputXML(),
            self.createOutputXML(),
            (
                xml.resource(
                    ref=spec.reference,
                    locator=resourceDB[self.__reserved[spec.reference]].locator
                    )
                for spec in self.getTask().resourceClaim
                # TODO: When TRs are in the resource DB, they can be included
                #       as well.
                if spec.typeName != taskRunnerResourceTypeName
            )
            ]

class TaskRunFactory:
    @staticmethod
    def createTaskrun(attributes: Mapping[str, str]) -> TaskRun:
        return TaskRun(attributes)

class TaskRunDB(Database[TaskRun]):
    baseDir = dbDir + '/taskruns'
    factory = TaskRunFactory()
    privilegeObject = 't'
    description = 'task run'
    uniqueKeys = ( 'id', )
taskRunDB = TaskRunDB()
shadowlib.taskRunDB = taskRunDB

def newTaskRun(task: Task) -> TaskRun:
    taskRun = TaskRun({'id': createInternalId()}, task)
    taskRunDB.add(taskRun)
    return taskRun

class RunInfo(XMLTag):
    '''Contains the ID strings required to uniquely identify a task run:
    jobId, taskId and runId.
    '''
    tagName = 'run'

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RunInfo):
            # pylint: disable=protected-access
            return self._properties == other._properties
        else:
            return NotImplemented

    def getTaskRun(self) -> TaskRun:
        '''Returns the task run object corresponding to the ID strings.
        If that task run does not exist, KeyError is raised.
        '''
        jobId = cast(str, self['jobId'])
        taskId = cast(str, self['taskId'])
        runId = cast(str, self['runId'])
        task = jobDB[jobId].getTask(taskId)
        if task is None:
            raise KeyError(f'no task named "{taskId}" in job {jobId}')
        return task.getRun(runId)

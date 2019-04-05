# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from typing import (
    AbstractSet, Callable, ClassVar, Iterable, Mapping, Optional, Sequence,
    Tuple, Type, TypeVar, cast
)
import logging

from twisted.internet import reactor

from softfab import joblib
from softfab.config import dbDir, syncDelay
from softfab.connection import ConnectionStatus
from softfab.databaselib import Database, RecordObserver
from softfab.projectlib import project
from softfab.resourcelib import ResourceBase
from softfab.restypelib import taskRunnerResourceTypeName
from softfab.shadowlib import ShadowRun, shadowDB
from softfab.statuslib import (
    DBStatusModelGroup, StatusModel, StatusModelRegistry
)
from softfab.taskrunlib import TaskRun, taskRunDB
from softfab.timelib import getTime
from softfab.utils import abstract, cachedProperty, parseVersion
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XML, XMLAttributeValue, XMLContent, xml

Task = joblib.Task

class RequestFactory:
    @staticmethod
    def createRequest(attributes: Mapping[str, str]) -> '_TaskRunnerData':
        return _TaskRunnerData(attributes)

class TaskRunnerFactory:
    @staticmethod
    def createTaskrunner(attributes: Mapping[str, str]) -> 'TaskRunner':
        return TaskRunner(attributes)

class TaskRunnerDB(Database['TaskRunner']):
    baseDir = dbDir + '/taskrunners'
    factory = TaskRunnerFactory()
    privilegeObject = 'tr'
    description = 'Task Runner'
    uniqueKeys = ( 'id', )
taskRunnerDB = TaskRunnerDB()

class _RunInfo(XMLTag):
    '''Contains the ID strings required to uniquely identify a task run:
    jobId, taskId and runId.
    '''
    tagName = 'run'

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _RunInfo):
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
        task = joblib.jobDB[jobId].getTask(taskId)
        if task is None:
            raise KeyError('no task named "%s" in job %s' % (taskId, jobId))
        return task.getRun(runId)

class _TaskRunnerData(XMLTag):
    '''This class represents a request of a Task Runner.
    It is also a part of a Task Runner database record.
    '''
    tagName = 'data'

    def __init__(self, properties: Mapping[str, XMLAttributeValue]):
        XMLTag.__init__(self, properties)

        # COMPAT 2.16: Rename 'runnerId' to 'id'.
        runnerId = self._properties.get('runnerId')
        if runnerId is not None:
            self._properties['id'] = runnerId
            del self._properties['runnerId']

        # COMPAT 2.x.x: Backward compatibility hack to cut off the host from
        #               runnerId.
        #               We have to change the sync protocol to fix this.
        if cast(str, self._properties['runnerVersion']).startswith('2.'):
            runnerId = cast(str, self._properties['id'])
            dot = runnerId.rfind('.')
            if dot != -1:
                self._properties['host'] = runnerId[ : dot]
                self._properties['id'] = runnerId[dot + 1 : ]

        self._properties.setdefault('host', '?')
        self.__run = cast(_RunInfo, None)
        self.__shadowRunId = None # type: Optional[str]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _TaskRunnerData):
            return (
                # pylint: disable=protected-access
                self._properties == other._properties and
                self.__run == other.__run and
                self.__shadowRunId == other.__shadowRunId
                )
        else:
            return NotImplemented

    @cachedProperty
    def version(self) -> Tuple[int, int, int]:
        '''Tuple of 3 integers representing the Task Runner version.
        '''
        return parseVersion(cast(str, self._properties['runnerVersion']))

    def _setTarget(self, attributes: Mapping[str, str]) -> None:
        # COMPAT 2.16: Ignore target coming from TR.
        pass

    def _addCapability(self, attributes: Mapping[str, str]) -> None:
        # COMPAT 2.16: Ignore capabilities coming from TR.
        pass

    def _setRun(self, attributes: Mapping[str, str]) -> None:
        self.__run = _RunInfo(attributes)

    def _setShadowrun(self, attributes: Mapping[str, str]) -> None:
        self.__shadowRunId = attributes['shadowId']

    def getId(self) -> str:
        return cast(str, self._properties['id'])

    def hasExecutionRun(self) -> bool:
        '''Returns True if the Task Runner reported it is running an execution
        run, False if it reported it is not running anything.
        '''
        return self.__run is not None

    def getExecutionRun(self) -> Optional[TaskRun]:
        '''Returns the execution run the Task Runner reported it is currently
        running, or None if it is not running an execution run.
        If the run it reports to be running does not exist, KeyError is raised.
        '''
        if self.__run is None:
            # Not running anything.
            return None
        else:
            return self.__run.getTaskRun()

    def getExecutionRunId(self) -> Optional[str]:
        '''Returns ID corresponding to the execution run the Task Runner
        reported it is currently running, or None if it is not running an
        execution run.
        If the run it reports to be running does not exist, KeyError is raised.
        '''
        taskRun = self.getExecutionRun()
        if taskRun is None:
            return None
        else:
            return taskRun.getId()

    def getShadowRun(self) -> Optional[ShadowRun]:
        '''Returns the shadow run the Task Runner reported it is currently
        running, or None if it is not running a shadow run.
        If the shadow run it reports to be running does not exist, KeyError
        is raised.
        '''
        if self.__shadowRunId is None:
            # Not running anything.
            return None
        else:
            return shadowDB[self.__shadowRunId]

    def getShadowRunId(self) -> Optional[str]:
        '''Returns ID corresponding to the shadow run the Task Runner reported
        it is currently running, or None if it is not running a shadow run.
        '''
        return self.__shadowRunId

    def _getContent(self) -> XMLContent:
        yield self.__run
        if self.__shadowRunId is not None:
            yield xml.shadowrun(shadowId = self.__shadowRunId)

RunT = TypeVar('RunT', TaskRun, ShadowRun)

class RunObserver(RecordObserver[RunT], ABC):
    '''Base class for monitoring the task run or shadow DB to keep track of
    which run a particular Task Runner is expected to be working on.
    '''
    db = abstract # type: ClassVar[Database]
    runType = abstract # type: ClassVar[str]

    def __init__(self,
                 taskRunner: 'TaskRunner',
                 callback: Callable[[Optional[RunT]], None]
                 ):
        RecordObserver.__init__(self)
        self.__taskRunner = taskRunner
        self.__callback = callback # type: Callable[[Optional[RunT]], None]
        self._run = None # type: Optional[RunT]
        self.db.addObserver(self)

    def retired(self) -> None:
        self.db.removeObserver(self)

    def reset(self) -> None:
        self._run = None

    def __shouldRun(self, run: RunT) -> bool:
        return (
            run.isRunning() and
            run.getTaskRunnerId() == self.__taskRunner.getId()
            )

    def _changeRun(self, newRun: Optional[RunT]) -> None:
        oldRun = self._run
        if oldRun is not None and newRun is not None:
            if oldRun.isRunning():
                logging.warning(
                    'Task Runner %s was running %s run %s and now '
                    '%s run %s is run by it; marking old %s run '
                    'as failed',
                    self.__taskRunner.getId(),
                    self.runType, oldRun.getId(),
                    self.runType, newRun.getId(),
                    self.runType
                    )
                oldRun.failed('Task Runner switched to a different run')
            else:
                logging.warning(
                    'Missed transition to non-running state on %s run %s',
                    self.runType, oldRun.getId()
                    )
        self._run = newRun

    def getRun(self) -> Optional[RunT]:
        return self._run

    def setRun(self, run: RunT) -> None:
        '''Called by the Task Runner when it parses its stored state.
        '''
        if self.__shouldRun(run):
            self._changeRun(run)
        else:
            logging.warning(
                'Task Runner %s thinks it is running %s run %s, '
                'but the %s run thinks not; ignoring Task Runner',
                self.__taskRunner.getId(),
                self.runType, run.getId(),
                self.runType
                )

    def added(self, record: RunT) -> None:
        self.updated(record)

    def removed(self, record: RunT) -> None:
        if self._run is not None and record.getId() == self._run.getId():
            self._changeRun(None)

    def updated(self, record: RunT) -> None:
        if self.__shouldRun(record):
            if self._run is None or record.getId() != self._run.getId():
                self._changeRun(record)
                self.__callback(record)
        else:
            if self._run is not None and record.getId() == self._run.getId():
                self._changeRun(None)
                self.__callback(None)

class ExecutionObserver(RunObserver[TaskRun]):
    db = taskRunDB
    runType = 'execution'

    def toXML(self) -> XMLContent:
        run = self._run
        if run is None:
            return None
        else:
            return xml.executionrun(runId=run.getId())

class ShadowObserver(RunObserver[ShadowRun]):
    db = shadowDB
    runType = 'shadow'

    def toXML(self) -> XMLContent:
        run = self._run
        if run is None:
            return None
        else:
            return xml.shadowrun(shadowId=run.getId())

class TaskRunner(ResourceBase):
    '''This is a database record with information about a Task Runner.
    This class contains the information which originates in the Control Center,
    while the _TaskRunnerData class contains the information as provided by
    the Task Runner on its last synchronization.

    Some information is present twice, like "which run is being executed":
    the version in _TaskRunnerData represents the point of view of the Task
    Runner, while the version in this class represents the point of view of
    the Control Center. Typically these will be aligned, but when they are not,
    it is useful to have access to both versions.

    To avoid lots of database writes, "last sync" is not stored in the database.
    This means that after a Control Center restart, the status of the Task
    Runner is unknown until it has either synchronized or timed out.
    TODO: It would be good to log not every sync, but at least state changes
          (when a TR becomes lost, for example). One problem we currently have
          is that TR status changes cannot be observed.
          Logging busy times might not be required, since that information is
          already stored in the task run database.
    '''
    tagName = 'taskrunner'
    boolProperties = ('exit',)

    @classmethod
    def create(cls, data: _TaskRunnerData) -> 'TaskRunner':
        '''Creates a new Task Runner record.
        The new record is returned and not added to the database.
        The new record still requires a call to sync(), because it is possible
        that the run it claims to be running is invalid.
        '''
        # pylint: disable=protected-access
        instance = cls({})
        instance.__data = data
        instance.__applyData()
        return instance

    def __init__(self, properties: Mapping[str, XMLAttributeValue]):
        # COMPAT 2.16: Rename 'paused' to 'suspended'.
        if 'paused' in properties:
            properties = dict(properties, suspended=properties['paused'])
            del properties['paused']

        ResourceBase.__init__(self, properties)
        self._properties.setdefault('description', '')
        self.__data = cast(_TaskRunnerData, None)
        self.__hasBeenInSync = False
        self.__executionObserver = ExecutionObserver(
            self, self.__shouldBeExecuting
            )
        self.__shadowObserver = ShadowObserver(
            self, self.__shouldBeRunningShadow
            )
        self.__lastSyncTime = getTime()
        self.__markLostCall = reactor.callLater(
            self.getLostTimeout(), self.markLost
            )

    def __applyData(self) -> None:
        """Copies properties of the data object to the main Task Runner record.
        This method exists to help in the transition from creating TR records
        on sync to having the user create them explicitly.
        """
        data = self.__data
        properties = self._properties
        for name in ('id', ):
            properties[name] = cast(str, data[name])

    def __getitem__(self, key: str) -> object:
        if key == 'lastSync':
            return getTime() - self.__lastSyncTime
        elif key == 'version':
            # Note: This field is intended to sort Task Runners by version.
            #       Use the supportsFeature() methods for checking what a
            #       particular Task Runner can do.
            return self.__data.version
        elif key == 'user':
            if self.isSuspended():
                return self.getChangedUser()
            taskRun = self.__executionObserver.getRun()
            if taskRun is not None:
                return 'T-' + taskRun.getId()
            shadowRun = self.__shadowObserver.getRun()
            if shadowRun is not None:
                return 'S-' + shadowRun.getId()
            return ''
        elif key in ('host', 'runnerVersion'):
            return self.__data[key]
        else:
            return super().__getitem__(key)

    def __str__(self) -> str:
        return self.toXML().flattenIndented()

    def _retired(self) -> None:
        if self.__markLostCall.active():
            self.__markLostCall.cancel()
        self.__markLostCall = None

        self.__executionObserver.retired()
        self.__executionObserver = cast(ExecutionObserver, None)

        self.__shadowObserver.retired()
        self.__shadowObserver = cast(ShadowObserver, None)

    @property
    def typeName(self) -> str:
        return taskRunnerResourceTypeName

    @property
    def locator(self) -> str:
        return cast(str, self.__data['host'])

    @ResourceBase.description.setter # type: ignore
    def description(self, value: str) -> None:
        self._properties['description'] = value
        self._notify()

    @ResourceBase.capabilities.setter # type: ignore
    def capabilities(self, value: Sequence[str]) -> None:
        self._capabilities = frozenset(value)
        self._notify()

    @property
    def targets(self) -> AbstractSet[str]:
        return self._capabilities & project.getTargets()

    def _setData(self, attributes: Mapping[str, str]) -> _TaskRunnerData:
        self.__data = _TaskRunnerData(attributes)
        return self.__data

    def _setExecutionrun(self, attributes: Mapping[str, str]) -> None:
        runId = attributes['runId']
        run = taskRunDB.get(runId)
        if run is None:
            logging.warning('Execution run %s does not exist', runId)
        else:
            self.__executionObserver.setRun(run)

    def _setShadowrun(self, attributes: Mapping[str, str]) -> None:
        shadowId = attributes['shadowId']
        shadowRun = shadowDB.get(shadowId)
        if shadowRun is None:
            logging.warning('Shadow run %s does not exist', shadowId)
        else:
            self.__shadowObserver.setRun(shadowRun)

    def __shouldBeExecuting(self, run: Optional[TaskRun]) -> None:
        '''Callback from ExecutionObserver.
        '''
        assert run is self.__executionObserver.getRun()
        # Write reference to current execution run to DB.
        self._notify()

    def __shouldBeRunningShadow(self, shadowRun: Optional[ShadowRun]) -> None:
        '''Callback from ShadowObserver.
        '''
        assert shadowRun is self.__shadowObserver.getRun()
        # Write reference to current shadow run to DB.
        self._notify()

    def markLost(self) -> None:
        '''Marks this Task Runner as lost and marks any task it was running as
        failed.
        '''
        observers = (
            self.__executionObserver,
            self.__shadowObserver
            ) # type: Iterable[RunObserver]
        for observer in observers:
            run = observer.getRun()
            if run is not None:
                logging.warning(
                    'Marking %s run %s as failed, '
                    'because its Task Runner "%s" is lost',
                    observer.runType, run.getId(), self.getId()
                    )
                run.failed('Task Runner is lost')

    def getWarnTimeout(self) -> int:
        """Returns the maximum time that may elapse until the
        TR gets the 'warning' status (=orange).
        This method is public so it can be overridden by the unittest.
        """
        warnTimeout = max(7, self.getSyncWaitDelay() + 2)
        return warnTimeout

    def getLostTimeout(self) -> int:
        """Returns the maximum time in seconds that may elapse until the
        TR gets the 'lost' status (=red).
        lostTimeout is at least 302 or more if syncDelay > 30
        This method is public so it can be overridden by the unittest.
        """
        lostTimeout = max(302, self.getSyncWaitDelay() * 10 + 2)
        return lostTimeout

    def getId(self) -> str:
        return self.__data.getId()

    def getLastSyncTime(self) -> int:
        return self.__lastSyncTime

    def getSyncWaitDelay(self) -> int:
        '''Returns the wait time in seconds before the Task Runner should
        synchronize with the Control Center again.
        '''
        return syncDelay

    def getMinimalDelay(self) -> int:
        '''Returns the minimum wait time in seconds the Task Runner can handle.
        '''
        return 1

    def getConnectionStatus(self) -> ConnectionStatus:
        sinceLastSync = getTime() - self.__lastSyncTime
        if sinceLastSync > self.getLostTimeout():
            return ConnectionStatus.LOST
        elif sinceLastSync > self.getWarnTimeout():
            return ConnectionStatus.WARNING
        elif self.__hasBeenInSync:
            return ConnectionStatus.CONNECTED
        else:
            return ConnectionStatus.UNKNOWN

    def getRun(self) -> Optional[TaskRun]:
        return self.__executionObserver.getRun()

    def getShadowRunId(self) -> Optional[str]:
        shadowRun = self.__shadowObserver.getRun()
        if shadowRun is None:
            return None
        else:
            return shadowRun.getId()

    def setExitFlag(self, flag: bool) -> None:
        self._properties['exit'] = flag
        self._notify()

    def shouldExit(self) -> bool:
        '''Returns True iff this Task Runner should exit as soon as it is
        not doing anything.
        '''
        return cast(bool, self._properties['exit'])

    def isReserved(self) -> bool:
        '''Returns True iff something has been assigned to this Task Runner.
        '''
        return self.__executionObserver.getRun() is not None \
            or self.__shadowObserver.getRun() is not None

    def deactivate(self, reason: str) -> None:
        '''Suspends this Task Runner because it is misbehaving.
        The given reason is logged so the operator can review it, correct
        the problem and then re-enable this Task Runner.
        '''
        logging.warning(
            'Deactivating malfunctioning Task Runner "%s": %s',
            self.getId(), reason
            )
        self.setSuspend(True, 'ControlCenter')

    def sync(self, data: _TaskRunnerData) -> bool:
        '''Synchronise database with data reported by the Task Runner.
        The sync time will be remembered, but not stored in the database.
        Returns True iff the run that the Task Runner reports should be aborted,
        for example because the user requested it or because it is not running
        the run the Control Center thinks it should be running.
        '''
        if data != self.__data:
            self.__data = data
            self._notify()
        self.__lastSyncTime = getTime()
        self.__hasBeenInSync = True
        if self.__markLostCall.active():
            self.__markLostCall.cancel()
        self.__markLostCall = reactor.callLater(
            self.getLostTimeout(), self.markLost
            )

        if data.hasExecutionRun() and data.getShadowRunId() is not None:
            self.deactivate(
                'it claims to be running both an execution task and '
                'a shadow task'
                )
            abort = True
        else:
            abort = False
        abort |= self.__enforceSync(
            self.__executionObserver, data.getExecutionRunId
            )
        abort |= self.__enforceSync(
            self.__shadowObserver, data.getShadowRunId
            )
        return abort

    def __enforceSync(self,
                      observer: RunObserver[RunT],
                      getId: Callable[[], Optional[str]]
                      ) -> bool:
        '''Checks if the Control Center's and Task Runner's view of the
        current task are the same and resolves the Control Center side of
        any conflicts.
        Returns True iff the run that the Task Runner reports should be aborted
        to resolve the Task Runner side of a conflict, or on user request.
        '''
        # Determine which run the Task Runner is running.
        try:
            trRunId = getId()
        except KeyError:
            # Reported run does not exist; use a dummy ID.
            trRunId = '?'
        # Determine which run the Control Center thinks should be running.
        ccRun = observer.getRun()
        # Resolve conflicts.
        if ccRun is None:
            return trRunId is not None
        else:
            if trRunId == ccRun.getId():
                return ccRun.isToBeAborted()
            else:
                logging.warning(
                    'Execution of %s run %s failed: '
                    'Task Runner "%s" is no longer executing it',
                    observer.runType, ccRun.getId(), self.getId()
                    )
                ccRun.failed('Task Runner stopped executing this task')
                return trRunId is not None

    def _endParse(self) -> None:
        super()._endParse()
        self.__applyData()

    def _getContent(self) -> XMLContent:
        yield super()._getContent()
        yield self.__data.toXML()
        yield self.__executionObserver.toXML()
        yield self.__shadowObserver.toXML()

    # Used by recomputeRunning:

    def _resetRuns(self) -> None:
        self.__executionObserver.reset()
        self.__shadowObserver.reset()

    def _initExecutionRun(self, run: TaskRun) -> None:
        self.__executionObserver.setRun(run)

    def _initShadowRun(self, run: ShadowRun) -> None:
        self.__shadowObserver.setRun(run)

def recomputeRunning() -> None:
    '''Scan the task run and shadow databases for running tasks.
    This is useful when:
    - jobs have been deleted manually
    - the task/shadow and Task Runner databases have somehow gone out of sync
    '''
    # pylint: disable=protected-access
    # The methods are protected on purpose, because no-one else should use them.
    for runner in taskRunnerDB:
        runner._resetRuns()
    for runs, setter in (
        ( taskRunDB, TaskRunner._initExecutionRun ),
        ( shadowDB, TaskRunner._initShadowRun ),
        ):
        for run in runs:
            if run.isRunning():
                runnerId = run.getTaskRunnerId()
                if runnerId is not None:
                    try:
                        runner = taskRunnerDB[runnerId]
                    except KeyError:
                        run.fail('Task Runner no longer exists')
                    else:
                        cast(Callable[[TaskRunner, RunT], None], setter)(
                            runner, run
                            )
    for runner in taskRunnerDB:
        runner._notify()

class TaskRunnerModel(StatusModel):

    __statusMap = {
        ConnectionStatus.LOST: 'error',
        ConnectionStatus.WARNING: 'warning',
        ConnectionStatus.CONNECTED: 'ok',
        ConnectionStatus.UNKNOWN: 'unknown',
        }

    @classmethod
    def getChildClass(cls) -> Optional[Type[StatusModel]]:
        return None

    def __init__(self, modelId: str, parent: 'TaskRunnerModelGroup'):
        self.__taskRunner = taskRunnerDB[modelId]
        StatusModel.__init__(self, modelId, parent)

    def __updated(self, record: TaskRunner) -> None:
        assert record is self.__taskRunner
        self._notify()

    def _registerForUpdates(self) -> None:
        self.__taskRunner.addObserver(self.__updated)

    def _unregisterForUpdates(self) -> None:
        self.__taskRunner.removeObserver(self.__updated)

    def formatStatus(self) -> XML:
        taskRunner = self.__taskRunner
        connectionStatus = taskRunner.getConnectionStatus()
        health = self.__statusMap[connectionStatus]
        if connectionStatus is ConnectionStatus.CONNECTED:
            executionRun = taskRunner.getRun()
            if executionRun is not None:
                alert = executionRun.getAlert()
                if alert:
                    # TODO: Replace by "alert" or by separate attribute.
                    health = 'inspect'
        return xml.status(
            health = health,
            reserved = 'true' if taskRunner.isReserved() else 'false',
            suspended = 'true' if taskRunner.isSuspended() else 'false'
            )

class TaskRunnerModelGroup(DBStatusModelGroup):
    childClass = TaskRunnerModel
    db = taskRunnerDB

# Since the current code does not support Task Runner changes being observed
# (see comment in TaskRunner docstring), I disabled the model registration.
# pylint: disable=pointless-statement
StatusModelRegistry#.addModelGroup(TaskRunnerModelGroup, 'taskrunner')

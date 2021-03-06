# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from pathlib import Path
from typing import (
    TYPE_CHECKING, AbstractSet, Callable, ClassVar, Collection, DefaultDict,
    Iterable, Iterator, Mapping, Optional, Set, Tuple, TypeVar, cast
)
import logging

from softfab.connection import ConnectionStatus
from softfab.databaselib import Database, DatabaseElem, RecordObserver
from softfab.paramlib import GetParent, ParamMixin, Parameterized, paramTop
from softfab.reactor import reactor
from softfab.restypelib import ResType, ResTypeDB, taskRunnerResourceTypeName
from softfab.taskrunlib import TaskRun, TaskRunDB
from softfab.timelib import getTime
from softfab.tokens import Token, TokenDB, TokenRole, TokenUser
from softfab.users import TaskRunnerUser
from softfab.utils import (
    IllegalStateError, abstract, cachedProperty, parseVersion
)
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLContent, xml

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from softfab.joblib import JobDB
else:
    JobDB = object


ResourceT = TypeVar('ResourceT', bound='ResourceBase')

class ResourceBase(XMLTag, ParamMixin, DatabaseElem):
    """Base class for Resource and TaskRunner.
    """
    tagName: ClassVar[str] = abstract
    boolProperties = ('suspended',)
    intProperties = ('changedtime',)

    def __init__(self, properties: Mapping[str, str], resTypeDB: ResTypeDB):
        # COMPAT 2.x.x: Make locator into a parameter.
        locator: Optional[str]
        if 'locator' in properties:
            properties = dict(properties)
            locator = properties.pop('locator')
        else:
            locator = None
        super().__init__(properties)
        if locator is not None:
            self.addParameter('locator', locator)
        self._resTypeDB = resTypeDB
        self._capabilities: AbstractSet[str] = set()

    def _addCapability(self, attributes: Mapping[str, str]) -> None:
        cast(Set[str], self._capabilities).add(attributes['name'])

    def _getContent(self) -> XMLContent:
        yield self._paramsToXML()
        for cap in self._capabilities:
            yield xml.capability(name = cap)

    def __getitem__(self, key: str) -> object:
        if key == 'type':
            return self.typeName
        elif key == 'capabilities':
            return sorted(self._capabilities)
        elif key == 'changedtime':
            return self.getChangedTime()
        elif key == 'changeduser':
            return self.getChangedUser()
        else:
            return super().__getitem__(key)

    def _propertiesToCopy(self) -> Iterator[str]:
        yield 'tokenId'
        yield 'suspended'
        yield 'changedtime'
        yield 'changeduser'

    def getParent(self, getFunc: Optional[GetParent]) -> Parameterized:
        return paramTop

    def copyState(self: ResourceT, resource: ResourceT) -> None:
        myProps = self._properties
        otherProps = resource._properties # pylint: disable=protected-access
        for propName in self._propertiesToCopy():
            value = otherProps.get(propName)
            if value is not None:
                myProps[propName] = value
        self._notify()

    def getId(self) -> str:
        return cast(str, self._properties['id'])

    @property
    def typeName(self) -> str:
        """The name of the resource type of this resource.
        The type could be defined in `resTypeDB` or be a reserved type.
        """
        raise NotImplementedError

    @property
    def resType(self) -> ResType:
        return self._resTypeDB[self.typeName]

    @property
    def description(self) -> str:
        """String that describes this resource to the user.
        """
        return cast(str, self._properties['description'])

    @property
    def capabilities(self) -> AbstractSet[str]:
        return self._capabilities

    @property
    def cost(self) -> int:
        """A numeric value that is used as a tie breaker when multiple resource
        assignments are possible: resources with a lower cost will be preferred
        over more costly alternatives.
        The goal is to increase the chance of being able to grant future
        resource reservations without having to wait for reserved resources
        to become available again.
        No meaning should be attached to the cost value except the ability
        to compare the sum of the costs of different resource selections.
        Different resources may have equal costs.
        """
        # Note: A more refined cost function is possible, but as a starting
        #       point we just take the number of capabilities as an indication
        #       of how valuable a resource is: more capabilities means it is
        #       more likely that it matches a resource spec that is not matched
        #       by other resources.
        return len(self._capabilities)

    def isFree(self) -> bool:
        """Returns True iff this resource is currently available."""
        return not (self.isReserved() or self.isSuspended())

    def isReserved(self) -> bool:
        """Returns True iff this resource is currently reserved."""
        raise NotImplementedError

    def isSuspended(self) -> bool:
        """Returns True iff this resource is currently suspended."""
        return cast(bool, self._properties['suspended'])

    def setSuspend(self, suspended: bool, user: str) -> None:
        """Sets the (new) suspend state on request of `user`.
        """
        if self._properties['suspended'] != suspended:
            self._properties['suspended'] = suspended
            self._properties['changedtime'] = getTime()
            self._properties['changeduser'] = user
            self._notify()

    def getChangedUser(self) -> Optional[str]:
        '''Returns the name of the user that suspended/resumed the TR as
        the last person.
        '''
        return cast(Optional[str], self._properties.get('changeduser'))

    def getChangedTime(self) -> Optional[int]:
        '''Returns the time at which the suspend state last changed.
        '''
        return cast(Optional[int], self._properties.get('changedtime'))

    def getConnectionStatus(self) -> ConnectionStatus:
        '''Gets a classification of the connection between this resource and
        the Control Center. The status can be `UNKNOWN` only for a short time
        after a Control Center restart.
        If the resource does not depend on any external service, the status
        is always `CONNECTED`.
        '''
        raise NotImplementedError

    def getRun(self) -> Optional[TaskRun]:
        """Returns the execution run that this resource is reserved by,
        or None if it is not currently reserved by an execution run.
        """
        raise NotImplementedError

class Resource(ResourceBase):
    """Represents an actual resource, which has an identity and state.
    """
    tagName = 'resource'

    def _propertiesToCopy(self) -> Iterator[str]:
        yield from super()._propertiesToCopy()
        yield 'reserved'

    @property
    def typeName(self) -> str:
        return cast(str, self._properties['type'])

    def getConnectionStatus(self) -> ConnectionStatus:
        return ConnectionStatus.CONNECTED

    def getRun(self) -> None:
        # TODO: It would be useful to be able to return the run, since then
        #       resources reserved by a run with alert status would show
        #       that alert status too.
        #       But currently resources only remember the user that reserved
        #       them, not the run. Even for Task Runners the run info is
        #       reconstructed rather than remembered.
        return None

    def isReserved(self) -> bool:
        return 'reserved' in self._properties

    def reserve(self, reservedBy: str) -> None:
        if 'reserved' in self._properties:
            logging.error(
                'Attempt to reserve resource "%s" that is already reserved',
                self.getId()
                )
        else:
            self._properties['reserved'] = reservedBy
            self._notify()

    def free(self) -> None:
        if 'reserved' in self._properties:
            del self._properties['reserved']
            self._notify()
        else:
            logging.error(
                'Attempt to free resource "%s" that is not reserved',
                self.getId()
                )

class RunInfo(XMLTag):
    '''Contains the ID strings required to uniquely identify a task run:
    jobId, taskId and runId.
    '''
    tagName = 'run'

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RunInfo):
            return self._properties == other._properties
        else:
            return NotImplemented

    def getTaskRun(self, jobDB: JobDB) -> TaskRun:
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

class TaskRunnerData(XMLTag):
    '''This class represents a request of a Task Runner.
    It is also a part of a Task Runner database record.
    '''
    tagName = 'data'

    def __init__(self, properties: Mapping[str, str]):
        super().__init__(properties)
        self._properties.setdefault('host', '?')
        self.__run = cast(RunInfo, None)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TaskRunnerData):
            return (
                # pylint: disable=protected-access
                self._properties == other._properties and
                self.__run == other.__run
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
        self.__run = RunInfo(attributes)

    def hasExecutionRun(self) -> bool:
        '''Returns True if the Task Runner reported it is running an execution
        run, False if it reported it is not running anything.
        '''
        return self.__run is not None

    def getExecutionRunId(self, jobDB: JobDB) -> Optional[str]:
        '''Returns ID corresponding to the execution run the Task Runner
        reported it is currently running, or None if it is not running an
        execution run.
        If the run it reports to be running does not exist, KeyError is raised.
        '''
        runInfo = self.__run
        if runInfo is None:
            return None
        else:
            return runInfo.getTaskRun(jobDB).getId()

    def _getContent(self) -> XMLContent:
        yield self.__run

class RequestFactory:
    @staticmethod
    def createRequest(attributes: Mapping[str, str]) -> TaskRunnerData:
        return TaskRunnerData(attributes)

class ExecutionObserver(RecordObserver[TaskRun]):
    '''Monitors the task run DB to keep track of which run a particular
    Task Runner is expected to be working on.
    '''

    def __init__(self,
                 taskRunner: 'TaskRunner',
                 callback: Callable[[Optional[TaskRun]], None]
                 ):
        super().__init__()
        self.__taskRunner = taskRunner
        self.__callback: Callable[[Optional[TaskRun]], None] = callback
        self._run: Optional[TaskRun] = None

    def reset(self) -> None:
        self._run = None

    def __shouldRun(self, run: TaskRun) -> bool:
        return (
            run.isRunning() and
            run.getTaskRunnerId() == self.__taskRunner.getId()
            )

    def _changeRun(self, newRun: Optional[TaskRun]) -> None:
        oldRun = self._run
        if oldRun is not None and newRun is not None:
            if oldRun.isRunning():
                logging.warning(
                    'Task Runner %s was running %s and now %s is run by it; '
                    'marking old run as failed',
                    self.__taskRunner.getId(), oldRun.getId(), newRun.getId()
                    )
                oldRun.failed('Task Runner switched to a different run')
            else:
                logging.warning(
                    'Missed transition to non-running state on run %s',
                    oldRun.getId()
                    )
        self._run = newRun

    def getRun(self) -> Optional[TaskRun]:
        return self._run

    def setRun(self, run: TaskRun) -> None:
        '''Called by the Task Runner when it parses its stored state.
        '''
        if self.__shouldRun(run):
            self._changeRun(run)
        else:
            logging.warning(
                'Task Runner %s thinks it is running %s, '
                'but the run thinks not; ignoring Task Runner',
                self.__taskRunner.getId(), run.getId(),
                )

    def added(self, record: TaskRun) -> None:
        self.updated(record)

    def removed(self, record: TaskRun) -> None:
        if self._run is not None and record.getId() == self._run.getId():
            self._changeRun(None)

    def updated(self, record: TaskRun) -> None:
        if self.__shouldRun(record):
            if self._run is None or record.getId() != self._run.getId():
                self._changeRun(record)
                self.__callback(record)
        else:
            if self._run is not None and record.getId() == self._run.getId():
                self._changeRun(None)
                self.__callback(None)

    def toXML(self) -> XMLContent:
        run = self._run
        if run is None:
            return None
        else:
            return xml.executionrun(runId=run.getId())

class TaskRunner(ResourceBase):
    '''This is a database record with information about a Task Runner.
    This class contains the information which originates in the Control Center,
    while the TaskRunnerData class contains the information as provided by
    the Task Runner on its last synchronization.

    Some information is present twice, like "which run is being executed":
    the version in TaskRunnerData represents the point of view of the Task
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
    enumProperties = {'status': ConnectionStatus}

    def __init__(self,
                 properties: Mapping[str, str],
                 resTypeDB: ResTypeDB,
                 taskRunDB: TaskRunDB,
                 token: Optional[Token]
                 ):
        # COMPAT 2.16: Rename 'paused' to 'suspended'.
        if 'paused' in properties:
            properties = dict(properties, suspended=properties['paused'])
            del properties['paused']

        if token is not None:
            assert token.role is TokenRole.RESOURCE, token
            assert token.getParam('resourceId') == properties['id'], token
        self.__token = token

        super().__init__(properties, resTypeDB)
        self.__taskRunDB = taskRunDB
        self._properties.setdefault('description', '')
        self._properties.setdefault('status', ConnectionStatus.NEW)
        self.__data: Optional[TaskRunnerData] = None
        self.__hasBeenInSync = False
        self.__executionObserver = ExecutionObserver(
            self, self.__shouldBeExecuting
            )
        self.__lastSyncTime = getTime()
        self.__markLostCall = None
        if self._properties['status'] is ConnectionStatus.CONNECTED:
            self.__startLostCallback()

    def _createToken(self, tokenDB: TokenDB) -> None:
        assert self.__token is None, self.__token
        self.__token = token = Token.create(TokenRole.RESOURCE, {
            'resourceId': self.getId()
            })
        tokenDB.add(token)
        self._properties['tokenId'] = token.getId()
        self._notify()

    def copyState(self, runner: 'TaskRunner') -> None: # pylint: disable=arguments-differ
        # pylint: disable=protected-access
        self.__data = runner.__data
        self.__token = runner.__token
        self._properties['status'] = runner._properties['status']
        self.__hasBeenInSync = runner.__hasBeenInSync
        self.__lastSyncTime = runner.__lastSyncTime
        # Do this last, since it includes the call to _notify().
        super().copyState(runner)

    def __getitem__(self, key: str) -> object:
        if key == 'lastSync':
            if self.__hasBeenInSync:
                return getTime() - self.__lastSyncTime
            else:
                return None
        elif key == 'version':
            # Note: This field is intended to sort Task Runners by version.
            #       Use the supportsFeature() methods for checking what a
            #       particular Task Runner can do.
            data = self.__data
            if data is None:
                return (0, 0, 0)
            else:
                return data.version
        elif key in ('host', 'runnerVersion'):
            data = self.__data
            if data is None:
                return '?'
            else:
                return data[key]
        else:
            return super().__getitem__(key)

    def __str__(self) -> str:
        return self.toXML().flattenIndented()

    def _retired(self) -> None:
        self.__cancelLostCallback()
        self.__failRun('removed')

    @property
    def typeName(self) -> str:
        return taskRunnerResourceTypeName

    if not TYPE_CHECKING:
        # This construct isn't understood by mypy 0.701.

        @ResourceBase.description.setter
        def description(self, value: str) -> None:
            self._properties['description'] = value
            self._notify()

        @ResourceBase.capabilities.setter
        def capabilities(self, value: Iterable[str]) -> None:
            self._capabilities = frozenset(value)
            self._notify()

    @property
    def token(self) -> Token:
        """The authentication token for this Task Runner.

        @raise IllegalStateError: When this property is requested from
            a Task Runner that doesn't have a token. Only Task Runners
            that are in the Task Runner DB have tokens.
        """
        token = self.__token
        if token is None:
            raise IllegalStateError(f'Task Runner {self.getId()} has no token')
        else:
            return token

    def _setData(self, attributes: Mapping[str, str]) -> TaskRunnerData:
        self.__data = TaskRunnerData(attributes)
        return self.__data

    def _setExecutionrun(self, attributes: Mapping[str, str]) -> None:
        runId = attributes['runId']
        run = self.__taskRunDB.get(runId)
        if run is None:
            logging.warning('Execution run %s does not exist', runId)
        else:
            self.__executionObserver.setRun(run)

    def __shouldBeExecuting(self, run: Optional[TaskRun]) -> None:
        '''Callback from ExecutionObserver.
        '''
        assert run is self.__executionObserver.getRun()
        # Write reference to current execution run to DB.
        self._notify()

    def _startObservingExecution(self) -> None:
        self.__taskRunDB.addObserver(self.__executionObserver)

    def _stopObservingExecution(self) -> None:
        self.__taskRunDB.removeObserver(self.__executionObserver)

    def __startLostCallback(self) -> None:
        """Start mark-as-lost timer."""
        assert self.__markLostCall is None
        self.__markLostCall = reactor.callLater(
            self.getLostTimeout(), self.markLost
            )

    def __cancelLostCallback(self) -> None:
        """Stops mark-as-lost timer if it's active."""
        call = self.__markLostCall
        if call is not None:
            if call.active():
                call.cancel()
            self.__markLostCall = None

    def markLost(self) -> None:
        '''Marks this Task Runner as lost and marks any task it was running as
        failed.
        '''
        self._properties['status'] = ConnectionStatus.LOST
        self._notify()
        self.__failRun('lost')

    def __failRun(self, reason: str) -> None:
        """Marks any task this Task Runner was running as failed."""
        run = self.__executionObserver.getRun()
        if run is not None:
            logging.warning(
                'Marking run %s as failed, '
                'because its Task Runner "%s" is %s',
                run.getId(), self.getId(), reason
                )
            run.failed(f'Task Runner is {reason}')

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
        lostTimeout is at least 302, more if sync delay is over 30 seconds.
        This method is public so it can be overridden by the unittest.
        """
        lostTimeout = max(302, self.getSyncWaitDelay() * 10 + 2)
        return lostTimeout

    def getLastSyncTime(self) -> int:
        return self.__lastSyncTime

    def getSyncWaitDelay(self) -> int:
        '''Returns the wait time in seconds before the Task Runner should
        synchronize with the Control Center again.
        '''
        return 10

    def getMinimalDelay(self) -> int:
        '''Returns the minimum wait time in seconds the Task Runner can handle.
        '''
        return 1

    def getConnectionStatus(self) -> ConnectionStatus:
        savedStatus = cast(ConnectionStatus, self._properties['status'])
        if savedStatus is not ConnectionStatus.CONNECTED:
            return savedStatus
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
        return self.__executionObserver.getRun() is not None

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

    def sync(self, jobDB: JobDB, data: TaskRunnerData) -> bool:
        '''Synchronise database with data reported by the Task Runner.
        The sync time will be remembered, but not stored in the database.
        Returns True iff the run that the Task Runner reports should be aborted,
        for example because the user requested it or because it is not running
        the run the Control Center thinks it should be running.
        '''
        if data != self.__data or \
                self._properties['status'] is not ConnectionStatus.CONNECTED:
            self.__data = data
            self._properties['status'] = ConnectionStatus.CONNECTED
            self._notify()
        self.__lastSyncTime = getTime()
        self.__hasBeenInSync = True
        self.__cancelLostCallback()
        self.__startLostCallback()
        return self.__enforceSync(
            self.__executionObserver, lambda: data.getExecutionRunId(jobDB)
            )

    def __enforceSync(self,
                      observer: ExecutionObserver,
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
                    'Execution of run %s failed: '
                    'Task Runner "%s" is no longer executing it',
                    ccRun.getId(), self.getId()
                    )
                ccRun.failed('Task Runner stopped executing this task')
                return trRunId is not None

    def _getContent(self) -> XMLContent:
        yield super()._getContent()
        if self.__data is not None:
            yield self.__data.toXML()
        yield self.__executionObserver.toXML()

    # Used by recomputeRunning:

    def _resetRuns(self) -> None:
        self.__executionObserver.reset()

    def _initExecutionRun(self, run: TaskRun) -> None:
        self.__executionObserver.setRun(run)

class ResourceFactory:

    resTypeDB: ResTypeDB
    taskRunDB: TaskRunDB
    tokenDB: TokenDB

    def createResource(self, attributes: Mapping[str, str]) -> Resource:
        return Resource(attributes, self.resTypeDB)

    def createTaskrunner(self, attributes: Mapping[str, str]) -> TaskRunner:
        tokenId = attributes.get('tokenId')
        token = None
        if tokenId is not None:
            try:
                token = self.tokenDB.get(tokenId)
            except KeyError:
                pass
        runner = TaskRunner(attributes, self.resTypeDB, self.taskRunDB, token)
        if token is None:
            logging.error('Recreating token for Task Runner %s', runner.getId())
            # pylint: disable=protected-access
            runner._createToken(self.tokenDB)
        return runner

    def newResource(
            self, resourceId: str, resType: str, description: str,
            capabilities: Iterable[str]
            ) -> Resource:
        # pylint: disable=protected-access
        resource = Resource({
            'id': resourceId,
            'type': resType,
            'description': description,
            }, self.resTypeDB)
        resource._capabilities = frozenset(capabilities)
        return resource

    def newTaskRunner(self,
                      runnerId: str,
                      description: str,
                      capabilities: Iterable[str]
                      ) -> TaskRunner:
        '''Creates a new Task Runner record.
        The new record is returned and not added to the database.
        '''
        # pylint: disable=protected-access
        runner = TaskRunner({
            'id': runnerId,
            'description': description,
            }, self.resTypeDB, self.taskRunDB, None)
        runner._capabilities = frozenset(capabilities)
        return runner

class ResourceDB(Database[ResourceBase]):
    privilegeObject = 'r'
    description = 'resource'
    uniqueKeys = ( 'id', )

    factory: ResourceFactory

    def __init__(self, baseDir: Path):
        super().__init__(baseDir, ResourceFactory())
        self.__resourcesByType: DefaultDict[str, Set[str]] = \
                defaultdict(set)

    def _register(self, key: str, value: ResourceBase) -> None:
        self.__resourcesByType[value.typeName].add(key)
        super()._register(key, value)
        if isinstance(value, TaskRunner):
            # pylint: disable=protected-access
            value._startObservingExecution()

    def _unregister(self, key: str, value: ResourceBase) -> None:
        self.__resourcesByType[value.typeName].remove(key)
        super()._unregister(key, value)
        if isinstance(value, TaskRunner):
            # pylint: disable=protected-access
            value._stopObservingExecution()

    def _update(self, value: ResourceBase) -> None:
        resourcesByType = self.__resourcesByType
        resId = value.getId()
        newType = value.typeName
        if resId not in resourcesByType[newType]:
            # Resource type changed.
            # We don't know the old type, so we have to remove the resource
            # from all sets.
            for resources in resourcesByType.values():
                resources.discard(resId)
            resourcesByType[newType].add(resId)
        super()._update(value)

    def resourcesOfType(self, typeName: str) -> Collection[str]:
        """Return the IDs of all resources of the given type."""
        return self.__resourcesByType[typeName]

    def iterTaskRunners(self) -> Iterator[TaskRunner]:
        """Iterates through all Task Runner records.
        """
        for resourceId in self.resourcesOfType(taskRunnerResourceTypeName):
            yield cast(TaskRunner, self[resourceId])

    def getTaskRunner(self, runnerID: str) -> TaskRunner:
        """Returns a Task Runner record for the given ID.
        Raises KeyError if the ID does not exist or belongs to a resource
        that is not a Task Runner.
        """
        try:
            resource = self[runnerID]
        except KeyError as ex:
            raise KeyError(
                f'Task Runner "{runnerID}" does not exist (anymore?)'
                ) from ex
        if isinstance(resource, TaskRunner):
            return resource
        else:
            raise KeyError(f'resource "{runnerID}" is not a Task Runner')

    def runnerFromToken(self, user: TokenUser) -> TaskRunner:
        """Returns the Task Runner associated with a token user.

        Raises `KeyError` if the token user does not represent
        a Task Runner, for example because it represents a different
        type of resource.
        """
        owner = user.token.owner
        if isinstance(owner, TaskRunnerUser):
            return self.getTaskRunner(owner.name)
        else:
            raise KeyError('Token does not represent a Task Runner')

class TaskRunnerTokenProvider(RecordObserver[ResourceBase]):

    def __init__(self, tokenDB: TokenDB):
        self.__tokenDB = tokenDB

    def added(self, record: ResourceBase) -> None:
        if isinstance(record, TaskRunner):
            # pylint: disable=protected-access
            record._createToken(self.__tokenDB)

    def removed(self, record: ResourceBase) -> None:
        if isinstance(record, TaskRunner):
            self.__tokenDB.remove(record.token)

    def updated(self, record: ResourceBase) -> None:
        pass

def recomputeRunning(resourceDB: ResourceDB, taskRunDB: TaskRunDB) -> None:
    '''Scan the task run database for running tasks.
    This is useful when:
    - jobs have been deleted manually
    - the task and Task Runner databases have somehow gone out of sync
    '''
    # pylint: disable=protected-access
    # The methods are protected on purpose, because no-one else should use them.
    for runner in resourceDB.iterTaskRunners():
        runner._resetRuns()

    for run in taskRunDB:
        if run.isRunning():
            runnerId = run.getTaskRunnerId()
            if runnerId is None:
                logging.warning(
                    'No associated Task Runner for run %s',
                    run.getId()
                    )
                run.failed('No associated Task Runner')
                continue
            try:
                runner = resourceDB.getTaskRunner(runnerId)
            except KeyError as ex:
                message = ex.args[0]
                logging.warning(
                    'Task Runner for run %s disappeared: %s',
                    run.getId(), message
                    )
                run.failed(message)
            else:
                if runner.getConnectionStatus() == ConnectionStatus.LOST:
                    logging.warning(
                        'Task Runner "%s" for run %s was already lost',
                        runnerId, run.getId()
                        )
                    run.failed('Task Runner was lost')
                else:
                    runner._initExecutionRun(run)

    for runner in resourceDB.iterTaskRunners():
        runner._notify()

# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from collections import defaultdict
from typing import (
    TYPE_CHECKING, AbstractSet, Callable, ClassVar, Collection, DefaultDict,
    Iterable, Iterator, Mapping, Optional, Set, Tuple, TypeVar, cast
)
import logging

from twisted.internet import reactor

from softfab.config import dbDir, syncDelay
from softfab.connection import ConnectionStatus
from softfab.databaselib import Database, DatabaseElem, RecordObserver
from softfab.paramlib import GetParent, ParamMixin, Parameterized, paramTop
from softfab.projectlib import project
from softfab.restypelib import taskRunnerResourceTypeName
from softfab.shadowlib import ShadowRun, shadowDB
from softfab.taskrunlib import RunInfo, TaskRun, taskRunDB
from softfab.timelib import getTime
from softfab.tokens import Token, TokenRole, TokenUser, tokenDB
from softfab.userlib import TaskRunnerUser
from softfab.utils import abstract, cachedProperty, parseVersion
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLContent, xml

ResourceT = TypeVar('ResourceT', bound='ResourceBase')

class ResourceBase(ParamMixin, XMLTag, DatabaseElem):
    """Base class for Resource and TaskRunner.
    """
    tagName = abstract # type: ClassVar[str]
    boolProperties = ('suspended',)
    intProperties = ('changedtime',)

    def __init__(self, properties: Mapping[str, str]):
        ParamMixin.__init__(self)
        XMLTag.__init__(self, properties)
        DatabaseElem.__init__(self)
        self._capabilities = set() # type: AbstractSet[str]
        self.__token = None # type: Optional[Token]

    def _addCapability(self, attributes: Mapping[str, str]) -> None:
        cast(Set[str], self._capabilities).add(attributes['name'])

    def _getContent(self) -> XMLContent:
        yield self._paramsToXML()
        for cap in self._capabilities:
            yield xml.capability(name = cap)

    def __getitem__(self, key: str) -> object:
        if key == 'type':
            return self.typeName
        elif key == 'locator':
            return self.locator
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
    def locator(self) -> str:
        """String that can be used to access this resource.
        """
        raise NotImplementedError

    @property
    def description(self) -> str:
        """String that describes this resource to the user.
        """
        return cast(str, self._properties['description'])

    @property
    def capabilities(self) -> AbstractSet[str]:
        return self._capabilities

    @property
    def token(self) -> Token:
        token = self.__token
        if token is None:
            try:
                token = tokenDB[cast(str, self._properties['tokenId'])]
            except KeyError:
                token = Token.create(TokenRole.RESOURCE, {
                    'resourceId': self.getId()
                    })
                self._properties['tokenId'] = token.getId()
                self._notify()
            assert token.role is TokenRole.RESOURCE, token
            assert token.getParam('resourceId') == self.getId(), token
            self.__token = token
        return token

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
        Raises TypeError if `suspended` is not a bool.
        """
        if not isinstance(suspended, bool):
            raise TypeError(type(suspended))
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

    @classmethod
    def create(
            cls, resourceId: str, resType: str, locator: str, description: str,
            capabilities: Iterable[str]
            ) -> 'Resource':
        # pylint: disable=protected-access
        resource = cls({
            'id': resourceId,
            'type': resType,
            'description': description,
            'locator': locator,
            })
        resource._capabilities = frozenset(capabilities)
        return resource

    @property
    def typeName(self) -> str:
        return cast(str, self._properties['type'])

    @property
    def locator(self) -> str:
        return cast(str, self._properties['locator'])

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

class _TaskRunnerData(XMLTag):
    '''This class represents a request of a Task Runner.
    It is also a part of a Task Runner database record.
    '''
    tagName = 'data'

    def __init__(self, properties: Mapping[str, str]):
        XMLTag.__init__(self, properties)
        self._properties.setdefault('host', '?')
        self.__run = cast(RunInfo, None)
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
        self.__run = RunInfo(attributes)

    def _setShadowrun(self, attributes: Mapping[str, str]) -> None:
        self.__shadowRunId = attributes['shadowId']

    def hasExecutionRun(self) -> bool:
        '''Returns True if the Task Runner reported it is running an execution
        run, False if it reported it is not running anything.
        '''
        return self.__run is not None

    def getExecutionRunId(self) -> Optional[str]:
        '''Returns ID corresponding to the execution run the Task Runner
        reported it is currently running, or None if it is not running an
        execution run.
        If the run it reports to be running does not exist, KeyError is raised.
        '''
        runInfo = self.__run
        if runInfo is None:
            return None
        else:
            return runInfo.getTaskRun().getId()

    def getShadowRunId(self) -> Optional[str]:
        '''Returns ID corresponding to the shadow run the Task Runner reported
        it is currently running, or None if it is not running a shadow run.
        '''
        return self.__shadowRunId

    def _getContent(self) -> XMLContent:
        yield self.__run
        if self.__shadowRunId is not None:
            yield xml.shadowrun(shadowId = self.__shadowRunId)

class RequestFactory:
    @staticmethod
    def createRequest(attributes: Mapping[str, str]) -> _TaskRunnerData:
        return _TaskRunnerData(attributes)

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
    enumProperties = {'status': ConnectionStatus}

    @classmethod
    def create(cls,
               runnerId: str,
               description: str,
               capabilities: Iterable[str]
               ) -> 'TaskRunner':
        '''Creates a new Task Runner record.
        The new record is returned and not added to the database.
        '''
        # pylint: disable=protected-access
        runner = cls({
            'id': runnerId,
            'description': description,
            })
        runner._capabilities = frozenset(capabilities)
        return runner

    def __init__(self, properties: Mapping[str, str]):
        # COMPAT 2.16: Rename 'paused' to 'suspended'.
        if 'paused' in properties:
            properties = dict(properties, suspended=properties['paused'])
            del properties['paused']

        ResourceBase.__init__(self, properties)
        self._properties.setdefault('description', '')
        self._properties.setdefault('status', ConnectionStatus.NEW)
        self.__data = None # type: Optional[_TaskRunnerData]
        self.__hasBeenInSync = False
        self.__executionObserver = ExecutionObserver(
            self, self.__shouldBeExecuting
            )
        self.__shadowObserver = ShadowObserver(
            self, self.__shouldBeRunningShadow
            )
        self.__lastSyncTime = getTime()
        self.__markLostCall = None
        if self._properties['status'] is ConnectionStatus.CONNECTED:
            self.__startLostCallback()

    def copyState(self, runner: 'TaskRunner') -> None: # pylint: disable=arguments-differ
        # pylint: disable=protected-access
        self.__data = runner.__data
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

        self.__executionObserver.retired()
        self.__executionObserver = cast(ExecutionObserver, None)

        self.__shadowObserver.retired()
        self.__shadowObserver = cast(ShadowObserver, None)

    @property
    def typeName(self) -> str:
        return taskRunnerResourceTypeName

    @property
    def locator(self) -> str:
        data = self.__data
        if data is None:
            return '?'
        else:
            return cast(str, data['host'])

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
        observers = (
            self.__executionObserver,
            self.__shadowObserver
            ) # type: Iterable[RunObserver]
        for observer in observers:
            run = observer.getRun()
            if run is not None:
                logging.warning(
                    'Marking %s run %s as failed, '
                    'because its Task Runner "%s" is %s',
                    observer.runType, run.getId(), self.getId(), reason
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
        lostTimeout is at least 302 or more if syncDelay > 30
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
        return syncDelay

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
        if data != self.__data or \
                self._properties['status'] is not ConnectionStatus.CONNECTED:
            self.__data = data
            self._properties['status'] = ConnectionStatus.CONNECTED
            self._notify()
        self.__lastSyncTime = getTime()
        self.__hasBeenInSync = True
        self.__cancelLostCallback()
        self.__startLostCallback()

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

    def _getContent(self) -> XMLContent:
        yield super()._getContent()
        if self.__data is not None:
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

class ResourceFactory:

    @staticmethod
    def createResource(attributes: Mapping[str, str]) -> Resource:
        return Resource(attributes)

    @staticmethod
    def createTaskrunner(attributes: Mapping[str, str]) -> TaskRunner:
        return TaskRunner(attributes)

class ResourceDB(Database[ResourceBase]):
    baseDir = dbDir + '/resources'
    factory = ResourceFactory()
    privilegeObject = 'r'
    description = 'resource'
    uniqueKeys = ( 'id', )

    def __init__(self) -> None:
        super().__init__()
        self.__resourcesByType = \
                defaultdict(set) # type: DefaultDict[str, Set[str]]

    def _register(self, key: str, value: ResourceBase) -> None:
        self.__resourcesByType[value.typeName].add(key)
        super()._register(key, value)

    def _unregister(self, key: str, value: ResourceBase) -> None:
        self.__resourcesByType[value.typeName].remove(key)
        super()._unregister(key, value)

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

    def remove(self, value: ResourceBase) -> None:
        super().remove(value)
        if 'tokenId' in value._properties: # pylint: disable=protected-access
            tokenDB.remove(value.token)

resourceDB = ResourceDB()

def iterTaskRunners() -> Iterator[TaskRunner]:
    """Iterates through all Task Runner records.
    """
    for resourceId in resourceDB.resourcesOfType(taskRunnerResourceTypeName):
        yield cast(TaskRunner, resourceDB[resourceId])

def getTaskRunner(runnerID: str) -> TaskRunner:
    """Returns a Task Runner record for the given ID.
    Raises KeyError if the ID does not exist or belongs to a resource
    that is not a Task Runner.
    """
    try:
        resource = resourceDB[runnerID]
    except KeyError as ex:
        raise KeyError(
            f'Task Runner "{runnerID}" does not exist (anymore?)'
            ) from ex
    if isinstance(resource, TaskRunner):
        return resource
    else:
        raise KeyError(f'resource "{runnerID}" is not a Task Runner')

def runnerFromToken(user: TokenUser) -> TaskRunner:
    """Returns the Task Runner associated with a token user.

    Raises `KeyError` if the token user does not represent
    a Task Runner, for example because it represents a different
    type of resource.
    """
    owner = user.token.owner
    if isinstance(owner, TaskRunnerUser):
        return getTaskRunner(owner.name)
    else:
        raise KeyError('Token does not represent a Task Runner')

def recomputeRunning() -> None:
    '''Scan the task run and shadow databases for running tasks.
    This is useful when:
    - jobs have been deleted manually
    - the task/shadow and Task Runner databases have somehow gone out of sync
    '''
    # pylint: disable=protected-access
    # The methods are protected on purpose, because no-one else should use them.
    resourceDB.preload()
    for runner in iterTaskRunners():
        runner._resetRuns()
    def checkRunners(db: Database[RunT],
                     setter: Callable[[TaskRunner, RunT], None]
                     ) -> None:
        db.preload()
        for run in db:
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
                    runner = getTaskRunner(runnerId)
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
                        setter(runner, run)
    checkRunners(taskRunDB, TaskRunner._initExecutionRun)
    checkRunners(shadowDB, TaskRunner._initShadowRun)
    for runner in iterTaskRunners():
        runner._notify()

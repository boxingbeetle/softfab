# SPDX-License-Identifier: BSD-3-Clause

'''Implementation of the "reason for waiting" feature.
This informs the user of why a task isn't running yet.
'''

from abc import ABC
from enum import IntEnum
from typing import (
    TYPE_CHECKING, AbstractSet, Callable, ClassVar, Iterable, List, Optional,
    Sequence, Union
)

from softfab.connection import ConnectionStatus
from softfab.resreq import ResourceSpec
from softfab.utils import abstract, pluralize

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from softfab.resourcelib import ResourceBase, TaskRunner
else:
    ResourceBase = None
    TaskRunner = None

# Implementation of "Reason for waiting" feature:

StatusLevel = IntEnum('StatusLevel', 'FREE RESERVED SUSPENDED MISSING')

def statusLevelForResource(resource: ResourceBase) -> StatusLevel:
    if resource.getConnectionStatus() in (
            ConnectionStatus.LOST, ConnectionStatus.NEW
            ):
        return StatusLevel.MISSING
    elif resource.isReserved():
        return StatusLevel.RESERVED
    elif resource.isSuspended():
        return StatusLevel.SUSPENDED
    else:
        return StatusLevel.FREE

def _describeLevel(level: Union[StatusLevel, int]) -> str:
    if level == StatusLevel.RESERVED:
        return 'in use'
    elif level == StatusLevel.SUSPENDED:
        return 'suspended'
    elif level == StatusLevel.MISSING:
        return 'unavailable'
    else:
        return 'not defined'

class ReasonForWaiting:
    """Describes a reason why a task isn't running.
    """

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.description})'

    @property
    def priority(self) -> Sequence[int]:
        """A tuple of integers that indicates the priority of this reason:
        the reason with highest the tuple value will be presented to the user.
        """
        raise NotImplementedError

    @property
    def description(self) -> str:
        """A message for the user that describes this reason.
        """
        raise NotImplementedError

class InputReason(ReasonForWaiting):

    def __init__(self, inputs: Sequence[str]):
        super().__init__()
        self.__inputs = inputs

    @property
    def priority(self) -> Sequence[int]:
        return (6,)

    @property
    def description(self) -> str:
        inputs = self.__inputs
        return 'waiting for %s: %s' % (
            pluralize('input', len(inputs)),
            ', '.join(inputs)
            )

class ResourceMissingReason(ReasonForWaiting):

    def __init__(self, resourceId: str):
        super().__init__()
        self.__resourceId = resourceId

    @property
    def priority(self) -> Sequence[int]:
        return (0, 2)

    @property
    def description(self) -> str:
        return f'resource was deleted: {self.__resourceId}'

class ResourceReason(ReasonForWaiting, ABC):
    prioMinor: ClassVar[int] = abstract

    def __init__(self, level: StatusLevel):
        super().__init__()
        self._level = level

    @property
    def priority(self) -> Sequence[int]:
        return (5, self._level, self.prioMinor)

    @property
    def description(self) -> str:
        raise NotImplementedError

class ResourceCapsReason(ResourceReason):
    prioMinor = 0

    def __init__(self, typeName: str, level: StatusLevel):
        super().__init__(level)
        self.__type = typeName

    @property
    def description(self) -> str:
        return 'resources of type "%s" with required capabilities are %s' % (
            self.__type, _describeLevel(self._level + 1)
            )

class ResourceSpecReason(ResourceReason):
    prioMinor = 1

    def __init__(self, spec: ResourceSpec, level: StatusLevel):
        super().__init__(level)
        self.__spec = spec

    @property
    def description(self) -> str:
        return 'resources matching reference "%s" are %s' % (
            self.__spec.reference, _describeLevel(self._level + 1)
            )

class ResourceTypeReason(ResourceReason):
    prioMinor = 2

    def __init__(self, typeName: str, shortage: int, level: StatusLevel):
        super().__init__(level)
        self.__type = typeName
        self.__shortage = shortage

    @property
    def description(self) -> str:
        level = self._level
        if level == StatusLevel.FREE:
            return 'waiting for %s: %s' % (
                pluralize('resource', self.__shortage), self.__type
                )
        elif level == StatusLevel.RESERVED:
            return 'required %s suspended: %s' % (
                'resource is' if self.__shortage == 1 else 'resources are',
                self.__type
                )
        else:
            return f'not enough resources: {self.__type}'

class BoundReason(ReasonForWaiting):

    def __init__(self, boundRunnerId: str):
        super().__init__()
        self.__boundRunnerId = boundRunnerId

    @property
    def priority(self) -> Sequence[int]:
        return (4,)

    @property
    def description(self) -> str:
        return f'waiting for bound Task Runner: {self.__boundRunnerId}'

class _CapabilitiesReason(ReasonForWaiting, ABC):
    selectorMajor: ClassVar[int] = abstract

    def __init__(self,
                 missingOnAll: AbstractSet[str],
                 missingOnAny: AbstractSet[str]
                 ):
        super().__init__()
        self._missingOnAll = missingOnAll
        self._missingOnAny = missingOnAny

    @property
    def priority(self) -> Sequence[int]:
        return (
            self.selectorMajor,
            1,
            len(self._missingOnAll),
            len(self._missingOnAny)
            )

    @property
    def description(self) -> str:
        raise NotImplementedError

class TRCapsReason(_CapabilitiesReason):
    selectorMajor = 2

    @property
    def description(self) -> str:
        if self._missingOnAll:
            return 'no Task Runner has any of these capabilities: ' + \
                ', '.join(sorted(self._missingOnAll))
        else:
            return 'no Task Runner has all of these capabilities: ' + \
                ', '.join(sorted(self._missingOnAny))

class TRStateReason(ReasonForWaiting):

    def __init__(self, level: StatusLevel):
        super().__init__()
        self.__level = level

    @property
    def priority(self) -> Sequence[int]:
        return (2, 0, self.__level.value)

    @property
    def description(self) -> str:
        return 'all suitable Task Runners are ' + _describeLevel(self.__level)

class UnboundGroupCapsReason(_CapabilitiesReason):
    selectorMajor = 1

    @property
    def description(self) -> str:
        if self._missingOnAll:
            return 'no Task Runner has any of these group capabilities: ' + \
                ', '.join(sorted(self._missingOnAll))
        else:
            return 'no Task Runner has all of these group capabilities: ' + \
                ', '.join(sorted(self._missingOnAny))

class UnboundGroupStateReason(ReasonForWaiting):

    def __init__(self, level: StatusLevel):
        super().__init__()
        self.__level = level

    @property
    def priority(self) -> Sequence[int]:
        return (1, 0, self.__level.value)

    @property
    def description(self) -> str:
        return 'all Task Runners suitable for the task group are %s' % \
            _describeLevel(self.__level)

class BoundGroupTargetReason(ReasonForWaiting):

    def __init__(self, boundRunnerId: str, target: str):
        super().__init__()
        self.__boundRunnerId = boundRunnerId
        self.__target = target

    @property
    def priority(self) -> Sequence[int]:
        return (3, 2)

    @property
    def description(self) -> str:
        return f'bound Task Runner "{self.__boundRunnerId}" ' \
               f'does not support target "{self.__target}"'

class BoundGroupCapsReason(_CapabilitiesReason):
    selectorMajor = 3
    severity = 7

    def __init__(self, boundRunnerId: str, *args: AbstractSet[str]):
        self.__boundRunnerId = boundRunnerId
        super().__init__(*args)

    @property
    def description(self) -> str:
        assert self._missingOnAll == self._missingOnAny
        return 'bound Task Runner "%s" does not have group capabilities: %s' % (
            self.__boundRunnerId,
            ', '.join(sorted(self._missingOnAll or self._missingOnAny))
            )

class BoundGroupStateReason(ReasonForWaiting):

    def __init__(self, boundRunnerId: str, level: StatusLevel):
        super().__init__()
        self.__boundRunnerId = boundRunnerId
        self.__level = level

    @property
    def priority(self) -> Sequence[int]:
        return (3, 0, self.__level.value)

    @property
    def description(self) -> str:
        return f'bound Task Runner "{self.__boundRunnerId}" ' \
               f'is {_describeLevel(self.__level)}'

def topWhyNot(whyNot: Iterable[ReasonForWaiting]) -> ReasonForWaiting:
    """Returns the highest priority reason for waiting from `whyNot`.
    """
    return max(whyNot, key=lambda reason: reason.priority)

# TODO: This algorithm is similar to the one in
#       resourcelib.reserveResources(), maybe they can be combined?
#       (Another clue that a Task Runner is a special kind of resource.)

def _checkCapabilities(
        runners: Sequence[TaskRunner],
        whyNot: List[ReasonForWaiting],
        reasonFactory: Callable[[AbstractSet[str], AbstractSet[str]],
                                ReasonForWaiting],
        neededCaps: AbstractSet[str]
        ) -> Sequence[TaskRunner]:
    '''Filter out Task Runners without the required capabilities.
    '''
    foundRunners = []
    missingOnAny: AbstractSet[str] = set()
    missingOnAll: Optional[AbstractSet[str]] = None
    for runner in runners:
        missingCaps = neededCaps - runner.capabilities
        if missingCaps:
            missingOnAny |= missingCaps
            if missingOnAll is None:
                missingOnAll = missingCaps
            else:
                missingOnAll &= missingCaps
        else:
            foundRunners.append(runner)
    if not foundRunners:
        # There are no Task Runners with the right capabilities.
        if runners:
            assert missingOnAll is not None
            whyNot.append(reasonFactory(missingOnAll, missingOnAny))
    return foundRunners

def _checkState(
        runners: Sequence[TaskRunner],
        whyNot: List[ReasonForWaiting],
        reasonFactory: Callable[[StatusLevel], ReasonForWaiting],
        ) -> None:
    '''Report when Task Runner state is a reason a task is not running.
    '''
    level = min(
        (statusLevelForResource(runner) for runner in runners),
        default=StatusLevel.FREE
        )
    if level != StatusLevel.FREE:
        whyNot.append(reasonFactory(level))

def checkRunners(
        runners: Sequence[TaskRunner],
        neededCaps: AbstractSet[str],
        whyNot: List[ReasonForWaiting]
        ) -> Sequence[TaskRunner]:
    runners = _checkCapabilities(runners, whyNot, TRCapsReason, neededCaps)
    _checkState(runners, whyNot, TRStateReason)
    return runners

def checkGroupRunners(
        runners: Sequence[TaskRunner],
        neededCaps: AbstractSet[str],
        whyNot: List[ReasonForWaiting]
        ) -> Sequence[TaskRunner]:
    runners = _checkCapabilities(
        runners, whyNot, UnboundGroupCapsReason, neededCaps
        )
    _checkState(runners, whyNot, UnboundGroupStateReason)
    return runners

def checkBoundGroupRunner(
        boundRunner: TaskRunner,
        neededCaps: AbstractSet[str],
        whyNot: List[ReasonForWaiting]
        ) -> Sequence[TaskRunner]:
    boundRunnerId = boundRunner.getId()
    runners: Sequence[TaskRunner] = [ boundRunner ]
    runners = _checkCapabilities(
        runners, whyNot,
        lambda *args: BoundGroupCapsReason(boundRunnerId, *args),
        neededCaps
        )
    _checkState(
        runners, whyNot,
        lambda level: BoundGroupStateReason(boundRunnerId, level)
        )
    return runners

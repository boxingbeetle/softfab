# SPDX-License-Identifier: BSD-3-Clause

from abc import abstractmethod
from enum import Enum
from typing import (
    TYPE_CHECKING, AbstractSet, ClassVar, Dict, Iterable, Mapping, Optional,
    Sequence, Set, Type, Union, cast
)

from softfab.resreq import ResourceClaim
from softfab.restypelib import taskRunnerResourceTypeName
from softfab.resultcode import ResultCode
from softfab.xmlgen import XMLContent, xml

if TYPE_CHECKING:
    from softfab.frameworklib import Framework
    from softfab.taskdeflib import TaskDef
else:
    Framework = object
    TaskDef = object


class TaskRunnerSet:

    def __init__(self) -> None:
        super().__init__()
        self._runners: Set[str] = set()

    def _addRunner(self, attributes: Mapping[str, str]) -> None:
        self._runners.add(attributes['id'])

    def _setRunners(self, runners: Iterable[str]) -> None:
        self._runners = set(runners)

    def getRunners(self) -> AbstractSet[str]:
        return self._runners

    def runnersAsXML(self) -> XMLContent:
        for runner in self._runners:
            yield xml.runner(id = runner)

class TaskStateMixin:
    intProperties: ClassVar[Sequence[str]] = ('starttime', 'stoptime')
    enumProperties: ClassVar[Mapping[str, Type[Enum]]] = {
        'result': ResultCode
        }

    _properties: Dict[str, Union[str, int, Enum]]

    def _getState(self) -> str:
        raise NotImplementedError

    def getAlert(self) -> Optional[str]:
        raise NotImplementedError

    def isWaiting(self) -> bool:
        return self._getState() == 'waiting'

    def isRunning(self) -> bool:
        return self._getState() == 'running'

    def isDone(self) -> bool:
        return self._getState() == 'done'

    def isCancelled(self) -> bool:
        return self._getState() == 'cancelled'

    def isExecutionFinished(self) -> bool:
        '''Returns True iff this task has finished running, or was cancelled.
        Note that a task that has finished execution might not have its result
        available yet if it is waiting for inspection.
        '''
        return self._getState() in ( 'done', 'cancelled' )

    def isWaitingForInspection(self) -> bool:
        return self.result is ResultCode.INSPECT

    def hasResult(self) -> bool:
        '''Returns True iff the result of this task run is available.
        '''
        result = self.result
        return result is not None and result is not ResultCode.INSPECT

    @property
    def result(self) -> Optional[ResultCode]:
        return cast(Optional[ResultCode], self._properties.get('result'))

class ResourceRequirementsMixin:

    @abstractmethod
    def getFramework(self) -> Framework:
        ...

    @abstractmethod
    def getDef(self) -> TaskDef:
        ...

    @property
    def resourceClaim(self) -> ResourceClaim:
        return self.getFramework().resourceClaim.merge(
            self.getDef().resourceClaim
            )

    def getNeededCaps(self) -> AbstractSet[str]:
        for spec in self.resourceClaim.iterSpecsOfType(
                taskRunnerResourceTypeName):
            return spec.capabilities
        return frozenset()

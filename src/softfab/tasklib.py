# SPDX-License-Identifier: BSD-3-Clause

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


class TaskRunnerSet:

    def __init__(self) -> None:
        self._runners = set() # type: Set[str]

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
    intProperties = ('starttime', 'stoptime') # type: ClassVar[Sequence[str]]
    enumProperties = {
        'result': ResultCode
        } # type: ClassVar[Mapping[str, Type[Enum]]]

    if TYPE_CHECKING:
        _properties = {} # type: Dict[str, Union[str, int, Enum]]

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
        available yet if it is waiting for extraction or inspection.
        '''
        return self._getState() in ( 'done', 'cancelled' )

    def isWaitingForInspection(self) -> bool:
        return self.getResult() is ResultCode.INSPECT

    def hasResult(self) -> bool:
        '''Returns True iff the result of this task run is available.
        '''
        result = self.getResult()
        return result is not None and result is not ResultCode.INSPECT

    def getResult(self) -> Optional[ResultCode]:
        return cast(ResultCode, self._properties.get('result'))

class ResourceRequirementsMixin:

    if TYPE_CHECKING:
        # pylint: disable=multiple-statements
        def getFramework(self) -> Framework: ...
        def getDef(self) -> TaskDef: ...

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

# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Sequence

from restypelib import taskRunnerResourceTypeName
from resultcode import ResultCode
from xmlgen import xml

class TaskRunnerSet:

    def __init__(self):
        self._runners = set()

    def _addRunner(self, attributes):
        self._runners.add(attributes['id'])

    def _setRunners(self, runners):
        self._runners = set(runners)

    def getRunners(self):
        return self._runners

    def runnersAsXML(self):
        for runner in self._runners:
            yield xml.runner(id = runner)

class TaskStateMixin:
    intProperties = ('starttime', 'stoptime') # type: ClassVar[Sequence[str]]

    def __init__(self):
        if 'result' in self._properties:
            # COMPAT 2.13: Map "blocked" and "dismissed" onto "cancelled".
            #              Start using enumProperties when this conversion
            #              is removed.
            result = self._properties['result']
            if result in ( 'blocked', 'dismissed' ):
                result = 'cancelled'

            self._properties['result'] = ResultCode.__members__[result.upper()]

    def _getState(self):
        raise NotImplementedError

    def getAlert(self):
        raise NotImplementedError

    def isWaiting(self):
        return self._getState() == 'waiting'

    def isRunning(self):
        return self._getState() == 'running'

    def isDone(self):
        return self._getState() == 'done'

    def isCancelled(self):
        return self._getState() == 'cancelled'

    def isExecutionFinished(self):
        '''Returns True iff this task has finished running, or was cancelled.
        Note that a task that has finished execution might not have its result
        available yet if it is waiting for extraction or inspection.
        '''
        return self._getState() in ( 'done', 'cancelled' )

    def isWaitingForInspection(self):
        return self.getResult() is ResultCode.INSPECT

    def hasResult(self):
        '''Returns True iff the result of this task run is available.
        '''
        result = self.getResult()
        return result is not None and result is not ResultCode.INSPECT

    def getResult(self):
        return self._properties.get('result')

class ResourceRequirementsMixin:

    @property
    def resourceClaim(self):
        return self.getFramework().resourceClaim.merge(
            self.getDef().resourceClaim
            )

    def getNeededCaps(self):
        for spec in self.resourceClaim.iterSpecsOfType(
                taskRunnerResourceTypeName):
            return spec.capabilities
        return frozenset()

# SPDX-License-Identifier: BSD-3-Clause

from typing import Optional, cast

from softfab.joblib import Task
from softfab.pagelinks import TaskIdArgs
from softfab.shadowlib import shadowDB
from softfab.webgui import pageLink
from softfab.xmlgen import XML


def getTaskStatus(task: Task) -> str:
    '''Returns a short string describing the current status of the given task
    or task run.
    '''
    if task.isDone():
        def extractingNow() -> bool:
            # Note: Looking up 'extractionRun' will trigger loading of the
            #       taskrun record, but this is only done for runs which
            #       have no result, so typically they are already loaded.
            extractionRunId = cast(Optional[str], task['extractionRun'])
            if extractionRunId is None:
                return False
            extractionRun = shadowDB.get(extractionRunId)
            if extractionRun is None:
                return False
            return extractionRun.isRunning()
        result = task.getResult()
        if result is None:
            if extractingNow():
                return 'busy'
            else:
                return 'unknown'
        else:
            return result.name.lower()
    elif task.isCancelled():
        return 'cancelled'
    elif task.isRunning():
        return task.getAlert() or 'busy'
    else:
        return 'idle'

def taskSummary(task: Task) -> XML:
    return pageLink(
        'Task',
        TaskIdArgs(jobId=task.getJob().getId(), taskName=task.getName())
        )[ task.getLatestRun().getSummary() or '(empty summary)' ]

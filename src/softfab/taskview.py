# SPDX-License-Identifier: BSD-3-Clause

from softfab.joblib import Task
from softfab.pagelinks import TaskIdArgs
from softfab.webgui import pageLink
from softfab.xmlgen import XML


def getTaskStatus(task: Task) -> str:
    '''Returns a short string describing the current status of the given task
    or task run.
    '''
    if task.isDone():
        result = task.getResult()
        if result is None:
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

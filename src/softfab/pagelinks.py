# SPDX-License-Identifier: BSD-3-Clause

from typing import Optional, Sequence

from softfab.configlib import configDB
from softfab.pageargs import BoolArg, PageArgs, SetArg, StrArg
from softfab.request import Request
from softfab.resourcelib import TaskRunner
from softfab.restypelib import resTypeDB, taskRunnerResourceTypeName
from softfab.shadowlib import shadowDB
from softfab.webgui import pageLink, pageURL
from softfab.xmlgen import XMLContent, XMLNode, txt, xhtml


class ProductDefIdArgs(PageArgs):
    '''Identifies a particular product definition.
    '''
    id = StrArg()

def createProductDetailsURL(productDefId: str) -> str:
    return pageURL(
        'ProductDetails',
        ProductDefIdArgs(id = productDefId)
        )

def createProductDetailsLink(productDefId: str) -> XMLNode:
    return pageLink('ProductDetails', ProductDefIdArgs(id = productDefId))[
        productDefId
        ]

class FrameworkIdArgs(PageArgs):
    '''Identifies a particular framework definition.
    '''
    id = StrArg()

def createFrameworkDetailsURL(frameworkId: str) -> str:
    return pageURL(
        'FrameworkDetails',
        FrameworkIdArgs(id = frameworkId)
        )

def createFrameworkDetailsLink(frameworkId: str)-> XMLNode:
    return pageLink('FrameworkDetails', FrameworkIdArgs(id = frameworkId))[
        frameworkId
        ]

class TaskDefIdArgs(PageArgs):
    '''Identifies a particular task definition.
    '''
    id = StrArg()

def createTaskDetailsLink(taskDefId: str) -> XMLNode:
    return pageLink('TaskDetails', TaskDefIdArgs(id = taskDefId))[
        taskDefId
        ]

class ConfigIdArgs(PageArgs):
    '''Identifies a particular configuration.
    '''
    configId = StrArg()

def createConfigDetailsLink(configId: str,
                            label: Optional[str] = None
                            ) -> XMLContent:
    if label is None:
        label = configId
    if configId in configDB:
        return pageLink('ConfigDetails', ConfigIdArgs(configId = configId))[
            label
            ]
    else:
        return label

class JobIdArgs(PageArgs):
    '''Identifies a particular job.
    '''
    jobId = StrArg()

class JobIdSetArgs(PageArgs):
    '''Identifies a set of jobs.
    '''
    jobId = SetArg()

def createJobURL(jobId: str) -> str:
    '''Returns a URL of a page that contains details about the given job.
    '''
    return pageURL('ShowReport', JobIdArgs(jobId = jobId))

def createJobLink(jobId: str) -> XMLNode:
    '''Returns a Link of a page that contains details about the given job.
    '''
    return pageLink('ShowReport', JobIdArgs(jobId = jobId))[
        jobId
        ]

def createJobsURL(jobIDs: Sequence[str]) -> str:
    '''Returns a URL of a page that contains details about the given jobs.
    '''
    if len(jobIDs) == 1:
        return createJobURL(jobIDs[0])
    else:
        # Note: This also works fine for zero jobs.
        return pageURL('ShowJobs', JobIdSetArgs(jobId=jobIDs))

class TaskIdArgs(JobIdArgs):
    '''Identifies a particular task.
    '''
    taskName = StrArg()

def createTaskInfoLink(jobId: str, taskName: str) -> XMLNode:
    return pageLink(
        'ShowTaskInfo', TaskIdArgs(jobId = jobId, taskName = taskName)
        )[ taskName ]

def createTaskLink(taskrunner: TaskRunner) -> XMLContent:
    run = taskrunner.getRun()
    if run is not None:
        return createTaskInfoLink(run.getJob().getId(), run.getName())

    shadowId = taskrunner.getShadowRunId()
    if shadowId is not None:
        shadowRecord = shadowDB[shadowId]
        url = shadowRecord.getURL()
        description = shadowRecord.getDescription()
        if url:
            return xhtml.a(href = url)[ description ]
        else:
            return txt(description)

    return '-'

class TaskIdSetArgs(PageArgs):
    '''Identifies a set of tasks.
    '''
    task = SetArg()

def createTaskHistoryLink(taskName: str) -> XMLNode:
    return pageLink('ReportTasks', TaskIdSetArgs(task = {taskName}))[
        'Show history of task ', xhtml.b[ taskName ]
        ]

class ResourceIdArgs(PageArgs):
    '''Identifies a resource.
    '''
    id = StrArg()

class TaskRunnerIdArgs(PageArgs):
    '''Identifies a Task Runner.
    '''
    runnerId = StrArg()

class CapFilterArgs(PageArgs):
    restype = StrArg(taskRunnerResourceTypeName)
    cap = StrArg('')

def createCapabilityLink(typeName: str, cap: str = '') -> XMLNode:
    return pageLink('Capabilities', CapFilterArgs(restype=typeName, cap=cap))[
        cap or resTypeDB[typeName].presentationName
        ]

def createTargetLink(target: str) -> XMLNode:
    return createCapabilityLink(taskRunnerResourceTypeName, target)

def createTaskRunnerDetailsLink(taskRunnerId: str) -> XMLContent:
    if not taskRunnerId:
        return '-'
    elif taskRunnerId == '?':
        return '?'
    else:
        return pageLink(
            'TaskRunnerDetails', TaskRunnerIdArgs(runnerId = taskRunnerId)
            )[ taskRunnerId ]

class UserIdArgs(PageArgs):
    '''Identifies a particular user.
    '''
    user = StrArg()

class AnonGuestArgs(PageArgs):
    """Value for the anonymous guest access setting.
    """
    anonguest = BoolArg()

def createUserDetailsURL(userId: str) -> str:
    return pageURL('UserDetails', UserIdArgs(user = userId))

def createUserDetailsLink(userId: str) -> XMLNode:
    return xhtml.a(href = createUserDetailsURL(userId))[ userId ]

class URLArgs(PageArgs):
    """Remembers a URL on this Control Center that we can return to.
    """
    url = StrArg(None)

def loginURL(req: Request) -> str:
    """Returns a URL of the Login page, so that it returns to the request's
    URL after the user has logged in.
    """
    return pageURL('Login', URLArgs(url=req.getURL()))

def logoutURL(req: Request) -> str:
    """Returns a URL of the Logout page, so that it returns to the request's
    URL after the user has logged out.
    """
    return pageURL('Logout', URLArgs(url=req.getURL()))

# SPDX-License-Identifier: BSD-3-Clause

from softfab.configlib import configDB
from softfab.pageargs import BoolArg, PageArgs, SetArg, StrArg
from softfab.restypelib import resTypeDB
from softfab.shadowlib import shadowDB
from softfab.taskrunnerlib import taskRunnerDB
from softfab.webgui import pageLink, pageURL
from softfab.xmlgen import txt, xhtml

class ProductDefIdArgs(PageArgs):
    '''Identifies a particular product definition.
    '''
    id = StrArg()

def createProductDetailsURL(productDefId):
    return pageURL(
        'ProductDetails',
        ProductDefIdArgs(id = productDefId)
        )

def createProductDetailsLink(productDefId):
    return pageLink('ProductDetails', ProductDefIdArgs(id = productDefId))[
        productDefId
        ]

class FrameworkIdArgs(PageArgs):
    '''Identifies a particular framework definition.
    '''
    id = StrArg()

def createFrameworkDetailsURL(frameworkId):
    return pageURL(
        'FrameworkDetails',
        FrameworkIdArgs(id = frameworkId)
        )

def createFrameworkDetailsLink(frameworkId):
    return pageLink('FrameworkDetails', FrameworkIdArgs(id = frameworkId))[
        frameworkId
        ]

class TaskDefIdArgs(PageArgs):
    '''Identifies a particular task definition.
    '''
    id = StrArg()

def createTaskDetailsLink(taskDefId):
    return pageLink('TaskDetails', TaskDefIdArgs(id = taskDefId))[
        taskDefId
        ]

class ConfigIdArgs(PageArgs):
    '''Identifies a particular configuration.
    '''
    configId = StrArg()

def createConfigDetailsLink(configId, label = None):
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

def createJobURL(jobId):
    '''Returns a URL of a page that contains details about the given job.
    '''
    return pageURL('ShowReport', JobIdArgs(jobId = jobId))

def createJobLink(jobId):
    '''Returns a Link of a page that contains details about the given job.
    '''
    return pageLink('ShowReport', JobIdArgs(jobId = jobId))[
        jobId
        ]

def createJobsURL(jobIDs):
    '''Returns a URL of a page that contains details about the given jobs,
    or None if there are no jobs.
    '''
    if len(jobIDs) == 0:
        return None
    elif len(jobIDs) == 1:
        return createJobURL(jobIDs[0])
    else:
        return pageURL('ShowJobs', JobIdSetArgs(jobId = jobIDs))

class TaskIdArgs(JobIdArgs):
    '''Identifies a particular task.
    '''
    taskName = StrArg()

def createTaskInfoLink(jobId, taskName):
    return pageLink(
        'ShowTaskInfo', TaskIdArgs(jobId = jobId, taskName = taskName)
        )[ taskName ]

def createTaskLink(taskrunner):
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

def createTaskHistoryLink(taskName):
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
    restype = StrArg(None)
    cap = StrArg('')

def createCapabilityLink(typeName, cap=''):
    return pageLink('Capabilities', CapFilterArgs(restype=typeName, cap=cap))[
        cap or resTypeDB[typeName]['presentation']
        ]

def createTaskRunnerDetailsLink(taskRunnerId):
    if not taskRunnerId:
        return '-'
    elif taskRunnerId == '?':
        return '?'
    elif taskRunnerId in taskRunnerDB:
        return pageLink(
            'TaskRunnerDetails', TaskRunnerIdArgs(runnerId = taskRunnerId)
            )[  taskRunnerId ]
    else:
        return txt(taskRunnerId)

class UserIdArgs(PageArgs):
    '''Identifies a particular user.
    '''
    user = StrArg()

class AnonGuestArgs(PageArgs):
    """Value for the anonymous guest access setting.
    """
    anonguest = BoolArg()

def createUserDetailsURL(userId):
    return pageURL('UserDetails', UserIdArgs(user = userId))

def createUserDetailsLink(userId):
    return xhtml.a(href = createUserDetailsURL(userId))[ userId ]

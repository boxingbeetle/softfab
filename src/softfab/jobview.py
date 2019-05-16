# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, Mapping, Optional, Tuple, cast

from softfab.StyleResources import styleRoot
from softfab.config import rootURL
from softfab.databaselib import RecordObserver
from softfab.datawidgets import (
    DataColumn, DataTable, DurationColumn, TimeColumn
)
from softfab.joblib import jobDB
from softfab.notification import sendNotification
from softfab.pagelinks import createJobURL
from softfab.projectlib import project
from softfab.resultcode import ResultCode
from softfab.schedulelib import scheduleDB
from softfab.schedulerefs import createScheduleDetailsURL
from softfab.sortedqueue import SortedQueue
from softfab.taskview import getTaskStatus
from softfab.userview import OwnerColumn
from softfab.webgui import Panel, cell
from softfab.xmlgen import XMLContent, xhtml

# High priority status codes are at the end of the list.
_resultList = (
    'ok', 'cancelled', 'warning', 'error', 'unknown', 'idle', 'busy', 'inspect'
    )

# The most urgent alert status should be last in the list.
alertList = ( 'attention', )

# Used by jobview to create the task status bar.
# This order reflects progress, so the status bar looks like a progress bar:
# it fills up from left to right.
statusList = (
    'ok', 'warning', 'error', 'cancelled', 'inspect', 'busy', 'unknown'
    ) + alertList + ( 'idle', )

_resultOrder = dict(
    ( statusCode, order )
    for order, statusCode in enumerate(
        cast(Tuple[Optional[str]], ( None, )) + _resultList + alertList
        )
    )
def combinedStatus(statuses):
    '''Find the most urgent of the given statuses.
    Returns a status name (string), or None if statuses was empty or all of
    them were None.
    '''
    return max(list(statuses) + [None], key=_resultOrder.__getitem__)

# Cache for getJobStatus().
_finalJobStatus = {} # type: Mapping[str, str]

def getJobStatus(job):
    '''Summarizes the current status of the given job by combining the task
    statuses into a single value.
    '''
    # Return cached status, if available.
    jobId = job.getId()
    status = _finalJobStatus.get(jobId)
    if status is None:
        status = combinedStatus(getTaskStatus(task) for task in job.iterTasks())
        if job.hasFinalResult():
            # Status will never change again, so store it.
            _finalJobStatus[jobId] = status
    return status

# Note: Originally "unfinishedJobs" and "resultlessJobs" were located in joblib,
#       but that led to problems with the circular import of joblib and tasklib.

class _UnfinishedJobs(SortedQueue):
    compareField = 'timestamp'

    def _filter(self, record):
        return not record.isExecutionFinished()

unfinishedJobs = _UnfinishedJobs(jobDB)

class _ResultlessJobs(SortedQueue):
    compareField = 'timestamp'

    def _filter(self, record):
        return not record.hasFinalResult()

resultlessJobs = _ResultlessJobs(jobDB)

def createStatusBar(tasks, length = 10):
    if len(tasks) == 0:
        return None
    elif len(tasks) <= length:
        return xhtml.table(class_ = 'statusfew')[
            xhtml.tbody[
                xhtml.tr[(
                    xhtml.td(class_ = getTaskStatus(task))
                    for task in tasks
                    )]
                ]
            ]
    else:
        statusFreq = dict.fromkeys(statusList, 0)
        for task in tasks:
            statusFreq[getTaskStatus(task)] += 1
        def iterBars():
            for status in statusList:
                freq = statusFreq[status]
                if freq != 0:
                    yield xhtml.td(
                        style = 'width:%d%%' % int(100 * freq / len(tasks)),
                        class_ = status
                        )[ str(freq) ]
        return xhtml.table(class_ = 'statusmany')[
            xhtml.tbody[
                xhtml.tr[ iterBars() ]
                ]
            ]

_scheduleIcon = styleRoot.addIcon('ScheduleSmall')
_scheduleIconGray = styleRoot.addIcon('ScheduleSmallD')

class _DescriptionColumn(DataColumn):
    keyName = 'description'

    def presentCell(self, record, *, table, **kwargs):
        if table.descriptionLink:
            yield xhtml.a(
                href = createJobURL(record.getId()),
                )[ record.getDescription() ]
        else:
            yield record.getDescription()

        scheduleId = record.getScheduledBy()
        if scheduleId is not None:
            schedule = scheduleDB.get(scheduleId)
            if schedule is None:
                icon = _scheduleIconGray
                url = None
            else:
                icon = _scheduleIcon
                url = createScheduleDetailsURL(scheduleId)
            yield xhtml.a(
                href = url,
                title = scheduleId,
                class_ = 'jobicon'
                )[ icon.present(**kwargs) ]

class _StatusColumn(DataColumn):
    label = 'Status'

    def presentCell(self, record, **kwargs):
        return cell(class_ = 'strong')[
            createStatusBar(record.getTaskSequence())
            ]

class TargetColumn(DataColumn):
    keyName = 'target'

    def presentCell(self, record, **kwargs):
        target = record.getTarget()
        return '-' if target is None else target

createTimeColumn = TimeColumn(
    label = 'Create Time', keyName = 'recent', keyDisplay = 'timestamp'
    )
targetColumn = TargetColumn.instance

class JobsTable(DataTable):
    bodyId = 'jobs'
    db = jobDB
    descriptionLink = True
    objectName = 'jobs'

    leadTimeColumn = DurationColumn(label = 'Lead Time', keyName = 'leadtime')
    statusColumn = _StatusColumn.instance

    def showTargetColumn(self):
        return project.showTargets

    def iterRowStyles(self, rowNr, record, **kwargs):
        yield getJobStatus(record)

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn]:
        yield createTimeColumn
        yield self.leadTimeColumn
        yield _DescriptionColumn.instance
        if self.showTargetColumn():
            yield targetColumn
        if project.showOwners:
            yield OwnerColumn.instance
        yield self.statusColumn

class JobsSubTable(JobsTable):
    sortField = None
    tabOffsetField = None
    printRecordCount = False

class CommentPanel(Panel):
    '''Presents the optional user comment (if any) on a panel.
    '''

    def __init__(self, comment):
        super().__init__()
        self.lines = comment.splitlines()

    def present(self, **kwargs):
        presentation = super().present(**kwargs)
        if presentation is None:
            return None
        else:
            return (
                xhtml.p[ 'User-specified comment:' ],
                presentation
                )

    def presentContent(self, **kwargs: object) -> XMLContent:
        return xhtml.br.join(self.lines)

class _JobOverviewPresenter:

    def singleLineSummary(self, jobId):
        job = jobDB[jobId]
        return 'Job Complete: %s (%s)' % (
            getJobStatus(job), job.getDescription()
            )

    def keyValue(self, jobId):
        '''Generates key-value pairs which give an overview of the most
        important properties of a job.
        This is used to create easily parseable files for external processes,
        such as mail filters.
        '''
        job = jobDB[jobId]
        yield 'Id', jobId
        yield 'URL', rootURL + createJobURL(jobId)
        for key, value in job.getParams().items():
            if key not in ( 'notify', 'notify-mode' ):
                yield 'param.' + key, value
        for index, taskRun in enumerate(job.getTaskSequence()):
            prefix = 'task.%d.' % (index + 1)
            for prop in ( 'name', 'state', 'result', 'summary' ):
                yield prefix + prop, str(taskRun[prop] or 'unknown')

class _JobNotificationObserver(RecordObserver):

    def __init__(self):
        RecordObserver.__init__(self)
        # TODO: Create a new presenter for each presentation and remove the
        #       jobId from the interface?
        self.presenter = _JobOverviewPresenter()

    def added(self, record):
        pass

    def updated(self, record):
        pass

    def removed(self, record):
        params = record.getParams()
        locator = params.get('notify')
        if locator is not None:
            mode = params.get('notify-mode', 'always')
            if mode == 'always' or (
                mode == 'onfail' and
                record.getFinalResult() is not ResultCode.OK
                ) or (mode == 'onerror' and
                record.getFinalResult() is ResultCode.ERROR):
                sendNotification(locator, self.presenter, record.getId())

resultlessJobs.addObserver(_JobNotificationObserver())

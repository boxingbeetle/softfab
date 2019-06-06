# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, Optional, cast

from softfab.Page import InvalidRequest, PageProcessor
from softfab.datawidgets import (
    DataColumn, DataTable, DurationColumn, TimeColumn
)
from softfab.joblib import Task, jobDB
from softfab.jobview import TargetColumn
from softfab.pagelinks import (
    JobIdArgs, TaskIdArgs, createTaskInfoLink, createTaskRunnerDetailsLink
)
from softfab.projectlib import project
from softfab.request import Request
from softfab.resourcelib import iterTaskRunners
from softfab.shadowlib import shadowDB
from softfab.shadowview import getShadowRunStatus
from softfab.taskview import getTaskStatus, taskSummary
from softfab.typing import Collection
from softfab.userview import OwnerColumn
from softfab.webgui import cell, maybeLink, pageLink
from softfab.xmlgen import XMLContent, xhtml


class TaskColumn(DataColumn[Task]):
    label = 'Task'
    keyName = 'name'

    def presentCell(self, record: Task, **kwargs: object) -> XMLContent:
        table = cast('TaskRunsTable', kwargs['table'])
        if table.taskNameLink:
            return createTaskInfoLink(record.getJob().getId(), record.getName())
        else:
            return record.getName()

class SummaryColumn(DataColumn[Task]):
    keyName = 'summary'

    def presentCell(self, record: Task, **kwargs: object) -> XMLContent:
        return taskSummary(record)

class ExtractedColumn(DataColumn[Task]):
    label = 'Data'
    cellStyle = 'nobreak'

    def presentCell(self, record: Task, **kwargs: object) -> XMLContent:
        proc = cast(PageProcessor, kwargs['proc'])
        dataLink = pageLink(
            'ExtractionDetails',
            TaskIdArgs(
                jobId = proc.args.jobId,
                taskName = record.getName()
                )
            )[ 'view data' ]
        extractionRunId = cast(Optional[str], record['extractionRun'])
        if extractionRunId is None:
            if record.isDone():
                # No extraction was scheduled after task completed execution,
                # but execution wrapper might have provided data.
                return dataLink
            elif record.isCancelled():
                # Execution will not run, so no data is available.
                return '-'
            else:
                # Data might become available later.
                return 'not yet'
        else:
            extractionRun = shadowDB.get(extractionRunId)
            if extractionRun is None:
                return dataLink
            else:
                # Extraction run still exists.
                logLabel, style = {
                    'waiting': ( 'waiting', 'idle'      ),
                    'running': ( 'running', 'busy'      ),
                    'error':   ( 'failed',  'error'     ),
                    'warning': ( 'warning', 'warning'   ),
                    'ok':      ( 'log',     None        ),
                    }[getShadowRunStatus(extractionRun)]
                return cell(class_ = style)[
                    dataLink, ' | ',
                    maybeLink(extractionRun.getURL())[ logLabel ]
                    ]

class ExportColumn(DataColumn[Task]):
    label = 'Export'

    def presentCell(self, record: Task, **kwargs: object) -> XMLContent:
        if not record.hasExport():
            return '-'
        if record.isDone():
            url = record.getExportURL()
            if url:
                return xhtml.a(href = url)[ 'Export' ]
            else:
                return 'location unknown'
        elif record.isCancelled():
            return '-'
        else:
            return 'not yet'

class AbortColumn(DataColumn[Task]):
    label = 'Abort'

    def presentCell(self, record: Task, **kwargs: object) -> XMLContent:
        if record.canBeAborted():
            proc = cast(PageProcessor, kwargs['proc'])
            return pageLink(
                'AbortTask',
                TaskIdArgs(
                    jobId = proc.args.jobId,
                    taskName = record.getName()
                    )
                )[ 'Abort' ]
        else:
            return '-'

class TaskRunsTable(DataTable[Task]):
    db = None
    objectName = 'tasks'
    taskNameLink = True
    startTimeColumn = TimeColumn[Task](
        label='Start Time', keyName='-starttime', keyDisplay='starttime'
        )
    durationColumn = DurationColumn[Task](keyName='duration')
    taskColumn = TaskColumn.instance
    targetColumn = TargetColumn[Task].instance
    ownerColumn = OwnerColumn[Task].instance
    summaryColumn = SummaryColumn.instance

    def iterRowStyles(self,
                      rowNr: int,
                      record: Task,
                      **kwargs: object
                      ) -> Iterator[str]:
        yield getTaskStatus(record)

    def showTargetColumn(self) -> bool:
        '''Returns True iff the target column should be included.
        Default implementation returns True iff there are multiple targets
        defined for this project.
        '''
        return project.showTargets

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn[Task]]:
        yield self.startTimeColumn
        yield self.durationColumn
        yield self.taskColumn
        if self.showTargetColumn():
            yield self.targetColumn
        if project.showOwners:
            yield self.ownerColumn
        yield self.summaryColumn

class TaskRunnerColumn(DataColumn[Task]):
    keyName = 'runner'

    def presentCell(self, record: Task, **kwargs: object) -> XMLContent:
        return createTaskRunnerDetailsLink(cast(str, record[self.keyName]))

class JobProcessorMixin:

    def initJob(self, req: Request[JobIdArgs]) -> None:
        jobId = req.args.jobId

        try:
            job = jobDB[jobId]
        except KeyError:
            raise InvalidRequest('No job exists with ID "%s"' % jobId)
        job.updateSummaries(tuple(iterTaskRunners()))

        self.job = job

class TaskProcessorMixin(JobProcessorMixin):

    def initTask(self, req: Request[TaskIdArgs]) -> None:
        self.initJob(req)

        taskName = req.args.taskName
        task = self.job.getTask(taskName)
        if task is None:
            raise InvalidRequest(
                'There is no task named "%s" in job %s'
                % (taskName, req.args.jobId)
                )

        self.task = task

class JobTaskRunsTable(TaskRunsTable):
    sortField = None
    tabOffsetField = None
    printRecordCount = False
    style = 'nostrong'

    priorityColumn = DataColumn[Task](
        keyName='priority', cellStyle='rightalign'
        )

    def getRecordsToQuery(self, proc: PageProcessor) -> Collection[Task]:
        return cast(JobProcessorMixin, proc).job.getTaskSequence()

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn[Task]]:
        proc = cast(PageProcessor, kwargs['proc'])
        tasks = self.getRecordsToQuery(proc)
        yield self.taskColumn
        if project['taskprio']:
            yield self.priorityColumn
        yield self.startTimeColumn
        yield self.durationColumn
        yield self.summaryColumn
        yield ExtractedColumn.instance
        yield TaskRunnerColumn.instance
        # TODO: If a task does not have a report yet, hasExport() returns False.
        #       This means that if all tasks are waiting, there is no export
        #       column, even though it may appear later.
        #       A better implementation would be to check whether any member
        #       of the set of Task Runners potentially capable of running the
        #       tasks writes its reports in a storage pool that is exportable.
        #       However, this is beyond what can easily be implemented now.
        if any(task.hasExport() for task in tasks):
            yield ExportColumn.instance
        if any(task.canBeAborted() for task in tasks):
            yield AbortColumn.instance

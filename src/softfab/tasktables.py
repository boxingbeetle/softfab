# SPDX-License-Identifier: BSD-3-Clause

from typing import Collection, Iterator, cast

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
from softfab.taskview import getTaskStatus, taskSummary
from softfab.userlib import UserDB
from softfab.userview import OwnerColumn
from softfab.webgui import pageLink
from softfab.xmlgen import XMLContent


class TaskColumn(DataColumn[Task]):
    label = 'Task'
    keyName = 'name'

    def presentCell(self, record: Task, **kwargs: object) -> XMLContent:
        table = cast(TaskRunsTable, kwargs['table'])
        if table.taskNameLink:
            return createTaskInfoLink(record.getJob().getId(), record.getName())
        else:
            return record.getName()

class SummaryColumn(DataColumn[Task]):
    keyName = 'summary'

    def presentCell(self, record: Task, **kwargs: object) -> XMLContent:
        return taskSummary(record)

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

    def iterRowStyles( # pylint: disable=unused-argument
                      self,
                      rowNr: int,
                      record: Task,
                      **kwargs: object
                      ) -> Iterator[str]:
        yield getTaskStatus(record)

    def showTargetColumn(self, **kwargs: object) -> bool:
        '''Returns True iff the target column should be included.
        Default implementation returns True iff there are multiple targets
        defined for this project.
        '''
        return project.showTargets

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn[Task]]:
        userDB: UserDB = getattr(kwargs['proc'], 'userDB')
        yield self.startTimeColumn
        yield self.durationColumn
        yield self.taskColumn
        if self.showTargetColumn(**kwargs):
            yield self.targetColumn
        if userDB.showOwners:
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
            raise InvalidRequest(f'No job exists with ID "{jobId}"')
        job.updateSummaries(tuple(iterTaskRunners()))

        self.job = job

class TaskProcessorMixin(JobProcessorMixin):

    def initTask(self, req: Request[TaskIdArgs]) -> None:
        self.initJob(req)

        taskName = req.args.taskName
        task = self.job.getTask(taskName)
        if task is None:
            raise InvalidRequest(
                f'There is no task named "{taskName}" in job {req.args.jobId}'
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
        yield TaskRunnerColumn.instance
        if any(task.canBeAborted() for task in tasks):
            yield AbortColumn.instance

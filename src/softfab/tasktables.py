# SPDX-License-Identifier: BSD-3-Clause

from softfab.config import enableSecurity
from softfab.datawidgets import (
    DataColumn, DataTable, DurationColumn, TimeColumn
    )
from softfab.jobview import targetColumn
from softfab.pagelinks import createTaskRunnerDetailsLink
from softfab.projectlib import project
from softfab.taskview import (
    AbortColumn, ExportColumn, ExtractedColumn, SummaryColumn, TaskColumn,
    getTaskStatus
    )
from softfab.userview import OwnerColumn

class TaskRunsTable(DataTable):
    db = None
    objectName = 'tasks'
    taskNameLink = True
    startTimeColumn = TimeColumn(
        label = 'Start Time', keyName = '-starttime', keyDisplay = 'starttime'
        )
    durationColumn = DurationColumn(keyName = 'duration')
    taskColumn = TaskColumn.instance
    ownerColumn = OwnerColumn.instance
    summaryColumn = SummaryColumn.instance

    def iterRowStyles(self, rowNr, record, **kwargs):
        yield getTaskStatus(record)

    def showTargetColumn(self):
        '''Returns True iff the target column should be included.
        Default implementation returns True iff there are multiple targets
        defined for this project.
        '''
        return project.showTargets()

    def iterColumns(self, **kwargs):
        yield self.startTimeColumn
        yield self.durationColumn
        yield self.taskColumn
        if self.showTargetColumn():
            yield targetColumn
        if enableSecurity:
            yield self.ownerColumn
        yield self.summaryColumn

class TaskRunnerColumn(DataColumn):
    keyName = 'runner'

    def presentCell(self, record, **kwargs):
        return createTaskRunnerDetailsLink(record[self.keyName])

class JobTaskRunsTable(TaskRunsTable):
    sortField = None
    tabOffsetField = None
    printRecordCount = False
    style = 'nostrong'

    priorityColumn = DataColumn(keyName = 'priority', cellStyle = 'rightalign')

    def getRecordsToQuery(self, proc):
        # Note: The table will not be displayed when the job ID is invalid,
        #       but this method will be called at the end of processing.
        job = proc.job
        return () if job is None else job.getTaskSequence()

    def iterColumns(self, proc, **kwargs):
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
        if any(task.hasExport() for task in self.getRecordsToQuery(proc)):
            yield ExportColumn.instance
        if not proc.job.hasFinalResult():
            yield AbortColumn.instance

# SPDX-License-Identifier: BSD-3-Clause

from datawidgets import DataColumn
from pagelinks import TaskIdArgs, createTaskInfoLink
from shadowlib import shadowDB
from shadowview import getShadowRunStatus
from webgui import cell, maybeLink, pageLink
from xmlgen import xhtml

def getTaskStatus(task):
    '''Returns a short string describing the current status of the given task
    or task run.
    '''
    if task.isDone():
        def extractingNow():
            # Note: Looking up 'extractionRun' will trigger loading of the
            #       taskrun record, but this is only done for runs which
            #       have no result, so typically they are already loaded.
            extractionRunId = task['extractionRun']
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

class TaskColumn(DataColumn):
    label = 'Task'
    keyName = 'name'

    def presentCell(self, record, table, **kwargs):
        if table.taskNameLink:
            return createTaskInfoLink(record.getJob().getId(), record.getName())
        else:
            return record.getName()

class SummaryColumn(DataColumn):
    keyName = 'summary'

    def presentCell(self, record, **kwargs):
        return record.getSummaryHTML()

class ExtractedColumn(DataColumn):
    label = 'Data'
    cellStyle = 'nobreak'

    def presentCell(self, record, proc, **kwargs):
        dataLink = pageLink(
            'ExtractionDetails',
            TaskIdArgs(
                jobId = proc.args.jobId,
                taskName = record.getName()
                )
            )[ 'view data' ]
        extractionRunId = record['extractionRun']
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

class ExportColumn(DataColumn):
    label = 'Export'

    def presentCell(self, record, **kwargs):
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

class AbortColumn(DataColumn):
    label = 'Abort'

    def presentCell(self, record, proc, **kwargs):
        if record.hasResult():
            return '-'
        else:
            return pageLink(
                'AbortTask',
                TaskIdArgs(
                    jobId = proc.args.jobId,
                    taskName = record.getName()
                    )
                )[ 'Abort' ]

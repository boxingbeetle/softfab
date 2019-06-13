# SPDX-License-Identifier: BSD-3-Clause

from collections import OrderedDict
from typing import Dict, Iterable, Iterator, Optional, Sequence, cast

from softfab.FabPage import FabPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.ReportMixin import ReportTaskArgs
from softfab.datawidgets import DataTable
from softfab.frameworklib import frameworkDB
from softfab.joblib import Task
from softfab.pageargs import ArgsCorrected
from softfab.pagelinks import (
    TaskIdArgs, TaskReportArgs, createFrameworkDetailsLink, createJobLink,
    createTaskDetailsLink, createTaskHistoryLink, createTaskRunnerDetailsLink
)
from softfab.paramview import ParametersTable
from softfab.productlib import Product
from softfab.productview import ProductTable
from softfab.projectlib import project
from softfab.request import Request
from softfab.resourceview import InlineResourcesTable
from softfab.resultlib import getData, getKeys
from softfab.selectview import valuesToText
from softfab.shadowlib import shadowDB
from softfab.shadowview import getShadowRunStatus
from softfab.taskdeflib import taskDefDB
from softfab.taskdefview import formatTimeout
from softfab.tasktables import JobTaskRunsTable, TaskProcessorMixin
from softfab.typing import Collection
from softfab.userlib import User, checkPrivilege
from softfab.webgui import (
    PropertiesTable, Table, Widget, cell, maybeLink, pageLink
)
from softfab.xmlgen import XMLContent, txt, xhtml

REPORT_SANDBOX = ' '.join('allow-' + perm for perm in (
    'forms', 'modals', 'popups', 'popups-to-escape-sandbox', 'scripts'
    ))
"""Browser permissions granted to reports.

This probably needs to be tweaked over time; please submit an issue
if you find this too restrictive or not restrictive enough.
"""

class Task_GET(FabPage['Task_GET.Processor', 'Task_GET.Arguments']):
    icon = 'IconReport'
    description = 'Task'

    class Arguments(TaskReportArgs):
        pass

    class Processor(TaskProcessorMixin, PageProcessor[Arguments]):
        def process(self, req: Request[TaskReportArgs], user: User) -> None:
            self.initTask(req)
            task = self.task

            reports = OrderedDict() # type: Dict[str, Optional[str]]
            reports['Overview'] = None
            reports['Data'] = None
            taskReports = tuple(task.iterReports())
            reports.update(taskReports)

            # Find report to display.
            report = req.args.report
            if report is None:
                active = taskReports[0][0] if taskReports else 'Overview'
            else:
                report = report.casefold()
                for label in reports:
                    if label.casefold() == report:
                        active = label
                        break
                else:
                    raise InvalidRequest('unknown report: "%s"' % report)
            if report != active.casefold():
                raise ArgsCorrected(req.args.override(report=active.casefold()))

            # pylint: disable=attribute-defined-outside-init
            self.reports = reports
            self.active = active

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/a')

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        if proc.active == 'Overview':
            yield SelfTaskRunsTable.instance
            yield InputTable.instance
            yield OutputTable.instance

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        if proc.active == 'Overview':
            yield SelfTaskRunsTable.instance

    def pageTitle(self, proc: Processor) -> str:
        return 'Task: %s' % proc.task.getName()

    def presentContent(self, proc: Processor) -> XMLContent:
        reports = proc.reports
        active = proc.active

        yield xhtml.div(class_='reporttabs')[(
            xhtml.div(class_='active' if active == label else None)[
                pageLink(self.name,
                            proc.args.override(report=label.casefold())
                            )[ label ]
                ]
            for label in reports
            )]

        if active == 'Overview':
            yield self.presentOverview(proc)
        elif active == 'Data':
            yield self.presentData(proc)
        else:
            yield xhtml.iframe(
                class_='report', src=reports[active], sandbox=REPORT_SANDBOX
                )

    def presentOverview(self, proc: Processor) -> XMLContent:
        yield SelfTaskRunsTable.instance.present(proc=proc)
        yield DetailsTable.instance.present(proc=proc)
        yield InputTable.instance.present(proc=proc)
        yield OutputTable.instance.present(proc=proc)
        yield xhtml.p[ createTaskHistoryLink(proc.args.taskName) ]

    def presentData(self, proc: Processor) -> XMLContent:
        taskName = proc.task.getName()
        yield xhtml.p[ 'Extracted data for task ', xhtml.b[ taskName ], ':' ]

        task = proc.task
        if task.isDone():
            yield ExtractedDataTable.instance.present(proc=proc)
        elif task.isCancelled():
            yield xhtml.p[ 'Task execution was cancelled.' ]
        else:
            yield xhtml.p[ 'No data yet.' ]

        extractionRunId = cast(Optional[str], task['extractionRun'])
        if extractionRunId is not None:
            extractionRun = shadowDB.get(extractionRunId)
            if extractionRun is not None:
                yield xhtml.p[
                    'Extraction run: ',
                    maybeLink(extractionRun.getURL())[
                        getShadowRunStatus(extractionRun)
                        ]
                    ]

        yield xhtml.p[
            pageLink('ExtractedData', ReportTaskArgs(task = ( taskName, )))[
                'Visualize trends of task ', xhtml.b[ taskName ]
                ]
            ]

taskParametersTable = ParametersTable('task')

class SelfTaskRunsTable(JobTaskRunsTable):
    taskNameLink = False
    widgetId = 'selfTaskRunsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc: PageProcessor) -> Collection[Task]:
        return [cast(TaskProcessorMixin, proc).task]

class DetailsTable(PropertiesTable):

    def presentCaptionParts(self, **kwargs: object) -> XMLContent:
        proc = cast(Task_GET.Processor, kwargs['proc'])
        taskName = proc.args.taskName
        jobId = proc.args.jobId
        yield 'Task ', (xhtml.b[ taskName ], ' is part of Job: ',
            createJobLink(jobId))

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(Task_GET.Processor, kwargs['proc'])
        task = proc.task
        run = task.getLatestRun()
        taskDef = task.getDef()
        taskDefId = taskDef.getId()
        frameworkId = cast(str, taskDef['parent'])
        tdLatest = taskDefDB.latestVersion(taskDefId)
        fdLatest = frameworkDB.latestVersion(frameworkId)

        yield 'Title', taskDef['title']
        yield 'Description', taskDef['description']
        yield 'Framework', (
            ( frameworkId, xhtml.br,
              'note: this framework does not exist anymore' )
            if fdLatest is None else (
                createFrameworkDetailsLink(frameworkId),
                None if fdLatest == task['fdKey'] else (
                    xhtml.br,
                    'note: version used in this job differs from latest version'
                    )
                )
            )
        yield 'Task definition', (
            ( taskDefId, xhtml.br,
              'note: this task definition does not exist anymore' )
            if tdLatest is None else (
                createTaskDetailsLink(taskDefId),
                None if tdLatest == task['tdKey'] else (
                    xhtml.br,
                    'note: version used in this job differs from latest version'
                    )
                )
            )
        yield 'Timeout', formatTimeout(run.timeoutMins)

        if project['reqtag']:
            yield 'Requirements', valuesToText(taskDef.getTagValues('sf.req'))
        yield 'Parameters', taskParametersTable.present(**kwargs)

        # Task Runner selection.
        selectedRunners, level = task.getRunners(), 'task'
        if not selectedRunners:
            selectedRunners, level = task.getJob().getRunners(), 'job'
        # Note that the TR selection setting only controls the UI, not the
        # dispatching mechanism, so it is possible to have jobs with TR
        # selection enabled even if the setting is disabled.
        if selectedRunners:
            yield 'Task Runner selection', (
                'selected for %s: ' % level,
                txt(', ').join(
                    createTaskRunnerDetailsLink(runner)
                    for runner in sorted(selectedRunners)
                    )
                )
        elif project['trselect']:
            yield 'Task Runner selection', '-'

        # TODO: List assigned resources.
        yield 'Resources', InlineResourcesTable.instance.present(
            claim=task.resourceClaim, **kwargs
            )

class TaskProcessor(TaskProcessorMixin, PageProcessor[TaskIdArgs]):

    def process(self, req: Request[TaskIdArgs], user: User) -> None:
        self.initTask(req)

class InputTable(ProductTable[TaskProcessor]):
    label = 'Input'
    hideWhenEmpty = False
    showProducers = True
    showConsumers = False
    showColors = True
    widgetId = 'inputTable'
    autoUpdate = True

    def presentCaptionParts(self, **kwargs: object) -> XMLContent:
        proc = cast(Task_GET.Processor, kwargs['proc'])
        taskName = proc.args.taskName
        yield 'Task ', xhtml.b[ taskName ], ' consumes the following inputs:'

    def getProducts(self, proc: TaskProcessor) -> Sequence[Product]:
        job = proc.job
        task = proc.task
        # Create list of inputs in alphabetical order.
        return [
            job.getProduct(prodName)
            for prodName in sorted(task.getInputs())
            ]

class OutputTable(ProductTable[TaskProcessor]):
    label = 'Output'
    hideWhenEmpty = False
    showProducers = False
    showConsumers = True
    showColors = True
    widgetId = 'outputTable'
    autoUpdate = True

    def presentCaptionParts(self, **kwargs: object) -> XMLContent:
        proc = cast(Task_GET.Processor, kwargs['proc'])
        taskName = proc.args.taskName
        yield 'Task ', xhtml.b[ taskName ], ' produces the following outputs:'

    def getProducts(self, proc: TaskProcessor) -> Sequence[Product]:
        job = proc.job
        task = proc.task
        # Create list of outputs in alphabetical order.
        return [
            job.getProduct(prodName)
            for prodName in sorted(task.getOutputs())
            ]

    def filterProducers(self,
                        proc: TaskProcessor,
                        producers: Iterable[str]
                        ) -> Iterator[str]:
        # Only show producer if it is our task.
        taskName = proc.args.taskName
        if taskName in producers:
            yield taskName

class ExtractedDataTable(Table):
    columns = 'Key', 'Value'

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(TaskProcessorMixin, kwargs['proc'])
        taskRun = proc.task.getLatestRun()
        taskRunId = taskRun.getId()
        taskName = taskRun.getName()
        for key in sorted(getKeys(taskName)):
            values = []
            for run, value in getData(taskName, [ taskRunId ], key):
                assert run == taskRunId
                values.append(value)
            if len(values) == 0:
                value = '-'
            else:
                assert len(values) == 1
                value = values[0]
            yield key, cell(class_ = 'rightalign')[value]
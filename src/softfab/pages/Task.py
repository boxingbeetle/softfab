# SPDX-License-Identifier: BSD-3-Clause

from collections import OrderedDict
from os.path import splitext
from typing import (
    Any, ClassVar, Collection, Dict, Iterable, Iterator, Optional, Sequence,
    cast
)
import re

from softfab.FabPage import FabPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.StyleResources import styleRoot
from softfab.artifacts import SANDBOX_RULES
from softfab.datawidgets import DataTable
from softfab.frameworklib import FrameworkDB
from softfab.joblib import Task
from softfab.pageargs import ArgsCorrected
from softfab.pagelinks import (
    TaskIdArgs, TaskReportArgs, createDataTrendsLink,
    createFrameworkDetailsLink, createJobLink, createTaskDetailsLink,
    createTaskHistoryLink, createTaskRunnerDetailsLink
)
from softfab.paramview import ParametersTable
from softfab.productlib import Product
from softfab.productview import ProductTable
from softfab.reportview import ReportPresenter, createPresenter
from softfab.request import Request
from softfab.resourceview import InlineResourcesTable
from softfab.taskdeflib import TaskDefDB
from softfab.taskdefview import formatTimeout
from softfab.taskrunlib import TaskRunDB
from softfab.tasktables import JobTaskRunsTable, TaskProcessorMixin
from softfab.userlib import User, UserDB, checkPrivilege
from softfab.webgui import PropertiesTable, Table, Widget, cell, pageLink
from softfab.xmlgen import XMLContent, xhtml

reLabelSplit = re.compile(r'[_-]')

def presentLabel(label: str) -> str:
    """Compute a good-looking tab label from the technical label.
    """
    root, ext_ = splitext(label)
    if root:
        # Note: Don't use the title() method, since that will capitalize the
        #       first letter in a word even if it is preceded by non-letters.
        return ' '.join(word[0].upper() + word[1:]
                        for word in reLabelSplit.split(root))
    else:
        return '(empty)'

openInNewTabIcon = styleRoot.addIcon('OpenInNewTab')

class Task_GET(FabPage['Task_GET.Processor', 'Task_GET.Arguments']):
    icon = 'IconReport'
    description = 'Task'

    class Arguments(TaskReportArgs):
        pass

    class Processor(TaskProcessorMixin, PageProcessor[Arguments]):

        frameworkDB: ClassVar[FrameworkDB]
        taskDefDB: ClassVar[TaskDefDB]
        taskRunDB: ClassVar[TaskRunDB]
        userDB: ClassVar[UserDB]

        async def process(self,
                          req: Request[TaskReportArgs],
                          user: User
                          ) -> None:
            self.initTask(req)
            run = self.task.getLatestRun()

            reports: Dict[str, Optional[str]] = OrderedDict()
            reports['Overview'] = None
            reports['Data'] = None
            taskReports = tuple(run.reports)
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
                    raise InvalidRequest(f'unknown report: "{report}"')
            if report != active.casefold():
                raise ArgsCorrected(req.args.override(report=active.casefold()))

            presenter: Optional[ReportPresenter] = None
            if reports[active] is not None:
                opener = run.reportOpener(active)
                if opener is not None:
                    presenter = createPresenter(opener, active)

            # pylint: disable=attribute-defined-outside-init
            self.reports = reports
            self.active = active
            self.presenter = presenter

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/a')

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        if proc.active == 'Overview':
            yield SelfTaskRunsTable.instance
            yield InputTable.instance
            yield OutputTable.instance

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Any]]:
        if proc.active == 'Overview':
            yield SelfTaskRunsTable.instance

    def presentHeadParts(self, **kwargs: object) -> XMLContent:
        yield super().presentHeadParts(**kwargs)

        proc = cast(Task_GET.Processor, kwargs['proc'])
        presenter = proc.presenter
        if presenter is not None:
            yield xhtml[presenter.headItems()].present(**kwargs)

    def pageTitle(self, proc: Processor) -> str:
        return 'Task: ' + proc.task.getName()

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(Task_GET.Processor, kwargs['proc'])
        reports = proc.reports
        active = proc.active
        presenter = proc.presenter

        yield xhtml.div(class_='reporttabs')[(
            xhtml.div(class_='active' if active == label else None)[
                pageLink(
                    self.name,
                    proc.args.override(report=label.casefold())
                    )[ presentLabel(label) ],
                None if url is None else xhtml.a(
                    href=url, target='_blank',
                    title='Open report in new tab'
                    )[ openInNewTabIcon.present(**kwargs) ]
                ]
            for label, url in reports.items()
            )]

        if presenter is not None:
            yield presenter.presentBody()
        elif active == 'Overview':
            yield self.presentOverview(**kwargs)
        elif active == 'Data':
            yield self.presentData(**kwargs)
        else:
            yield xhtml.iframe(
                class_='report', src=reports[active], sandbox=SANDBOX_RULES
                )

    def presentOverview(self, **kwargs: object) -> XMLContent:
        proc = cast(Task_GET.Processor, kwargs['proc'])
        yield SelfTaskRunsTable.instance.present(**kwargs)
        yield DetailsTable.instance.present(**kwargs)
        yield InputTable.instance.present(**kwargs)
        yield OutputTable.instance.present(**kwargs)
        yield xhtml.p[ createTaskHistoryLink(proc.args.taskName) ]

    def presentData(self, **kwargs: object) -> XMLContent:
        proc = cast(Task_GET.Processor, kwargs['proc'])
        taskName = proc.task.getName()
        yield xhtml.p[ 'Extracted data for task ', xhtml.b[ taskName ], ':' ]

        task = proc.task
        if task.isDone():
            yield ExtractedDataTable.instance.present(**kwargs)
        elif task.isCancelled():
            yield xhtml.p[ 'Task execution was cancelled.' ]
        else:
            yield xhtml.p[ 'No data yet.' ]

        yield xhtml.p[
            createDataTrendsLink(taskName)[
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
        tdLatest = proc.taskDefDB.latestVersion(taskDefId)
        fdLatest = proc.frameworkDB.latestVersion(frameworkId)

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

        yield 'Parameters', taskParametersTable.present(**kwargs)

        # Task Runner selection.
        selectedRunners, level = task.getRunners(), 'task'
        if not selectedRunners:
            selectedRunners, level = task.getJob().getRunners(), 'job'
        if selectedRunners:
            selection: XMLContent = (
                f'selected for {level}: ',
                xhtml[', '].join(
                    createTaskRunnerDetailsLink(runner)
                    for runner in sorted(selectedRunners)
                    )
                )
        else:
            selection = '-'
        yield 'Task Runner selection', selection

        # TODO: List assigned resources.
        yield 'Resources', InlineResourcesTable.instance.present(
            claim=task.resourceClaim, **kwargs
            )

class TaskProcessor(TaskProcessorMixin, PageProcessor[TaskIdArgs]):

    async def process(self, req: Request[TaskIdArgs], user: User) -> None:
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
        proc = cast(Task_GET.Processor, kwargs['proc'])
        taskRunDB = proc.taskRunDB
        taskRun = proc.task.getLatestRun()
        taskRunId = taskRun.getId()
        taskName = taskRun.getName()
        for key in sorted(taskRunDB.getKeys(taskName)):
            values = []
            for run, value in taskRunDB.getData(taskName, [ taskRunId ], key):
                assert run == taskRunId
                values.append(value)
            if len(values) == 0:
                value = '-'
            else:
                assert len(values) == 1
                value = values[0]
            yield (
                createDataTrendsLink(taskName, [key])[key],
                cell(class_='rightalign')[value]
                )

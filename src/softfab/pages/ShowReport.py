# SPDX-License-Identifier: BSD-3-Clause

from typing import (
    Any, ClassVar, Collection, Iterator, List, Mapping, Sequence, Tuple, cast
)

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.configlib import ConfigDB
from softfab.datawidgets import DataTable
from softfab.formlib import checkBox
from softfab.joblib import Job
from softfab.jobview import CommentPanel, JobsSubTable, presentJobCaption
from softfab.pagelinks import (
    JobIdArgs, TaskIdArgs, createTaskInfoLink, createTaskRunnerDetailsLink
)
from softfab.productlib import Product
from softfab.productview import ProductTable
from softfab.request import Request
from softfab.resourcelib import ResourceDB
from softfab.resourceview import getResourceStatus
from softfab.schedulelib import ScheduleDB
from softfab.tasktables import JobProcessorMixin, JobTaskRunsTable
from softfab.userlib import UserDB
from softfab.users import User, checkPrivilege
from softfab.webgui import Table, Widget, cell, pageLink, row
from softfab.xmlgen import XMLContent, xhtml


class JobProcessor(JobProcessorMixin, PageProcessor[JobIdArgs]):

    async def process(self, req: Request[JobIdArgs], user: User) -> None:
        self.initJob(req)

class SelfJobsTable(JobsSubTable):
    descriptionLink = False
    widgetId = 'selfJobsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc: PageProcessor) -> Iterator[Job]:
        assert isinstance(proc, JobProcessor), proc
        yield proc.job

class TaskRunsTable(JobTaskRunsTable):
    widgetId = 'taskRunsTable'
    autoUpdate = True

    def presentCaptionParts(self, **kwargs: object) -> XMLContent:
        proc = cast(ShowReport_GET.Processor, kwargs['proc'])
        return presentJobCaption(proc.configDB, proc.job)

class ShowReport_GET(FabPage['ShowReport_GET.Processor',
                             'ShowReport_GET.Arguments']):
    icon = 'IconReport'
    description = 'Job'
    children = ['AbortTask', 'Task']

    class Arguments(JobIdArgs):
        pass

    class Processor(JobProcessor):
        configDB: ClassVar[ConfigDB]
        scheduleDB: ClassVar[ScheduleDB]
        userDB: ClassVar[UserDB]

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/a')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Any]]:
        yield SelfJobsTable.instance
        yield TaskRunsTable.instance

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        job = proc.job
        yield SelfJobsTable.instance
        yield TaskRunsTable.instance
        yield OutputTable.instance
        if job.getRunners() or any(
                task.getRunners() for task in job.iterTasks()
                ):
            yield TaskRunnerTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ShowReport_GET.Processor, kwargs['proc'])
        jobId = proc.args.jobId
        job = proc.job
        tasks = job.getTaskSequence()

        yield SelfJobsTable.instance.present(**kwargs)
        yield TaskRunsTable.instance.present(**kwargs)

        if any(task.canBeAborted() for task in tasks):
            if any(task.isWaiting() for task in tasks):
                yield xhtml.p[
                    pageLink(
                        'AbortTask',
                        TaskIdArgs(jobId = jobId, taskName = '/all-waiting')
                        )[ 'Abort all waiting tasks' ]
                    ]
            yield xhtml.p[
                pageLink(
                    'AbortTask',
                    TaskIdArgs(jobId = jobId, taskName = '/all')
                    )[ 'Abort all unfinished tasks' ]
                ]

        yield CommentPanel(job.comment).present(**kwargs)
        yield InputTable.instance.present(**kwargs)
        yield OutputTable.instance.present(**kwargs)
        yield ParamTable.instance.present(**kwargs)
        if not job.hasFinalResult():
            # Note: We check hasFinalResult instead of isExecutionFinished
            #       because for postponed inspection it can be useful to know
            #       which Factory PC ran the task.
            yield TaskRunnerTable.instance.present(**kwargs)

        notify = job.getParams().get('notify')
        if notify:
            notifyMode = job.getParams().get('notify-mode', 'always')
            protocol, path = notify.split(':', 1)
            if protocol == 'mailto':
                if notifyMode == 'onfail':
                    notifyStr = ' (only on warning or error)'
                elif notifyMode == 'onerror':
                    notifyStr = ' (only on error)'
                else:
                    notifyStr = ''
                yield xhtml.p[
                    'Notify when job done: ',
                    xhtml.b[ path ],
                    notifyStr
                    ]

class ParamTable(Table):
    bodyId = 'params'
    columns = 'Task', 'Parameter', 'Value'
    hideWhenEmpty = True

    def presentCaptionParts(self, **kwargs: object) -> XMLContent:
        taskParams = cast(Mapping[str, Sequence[Tuple[bool, str, str]]],
                          kwargs['taskParams'])
        anyFinal = any(
            final
            for params in taskParams.values()
            for final, key, value in params
            )
        yield 'Job uses the following parameters:'
        if anyFinal:
            yield xhtml.br
            yield checkBox(onclick=f"document.getElementById('{self.bodyId}')"
                                   f".classList.toggle('showfinal')")[
                'Show final parameters'
                ].present(**kwargs)

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(JobProcessor, kwargs['proc'])
        jobId = proc.args.jobId
        taskParams = cast(Mapping[str, Sequence[Tuple[bool, str, str]]],
                          kwargs['taskParams'])
        for name, params in taskParams.items():
            first = True
            for final, key, value in params:
                cells: List[XMLContent] = []
                if first:
                    cells.append(cell(rowspan=len(params))[
                        createTaskInfoLink(jobId, name)
                        ])
                    first = False
                cells += [key, value]
                yield row(class_='final' if final else None)[cells]

    def present(self, **kwargs: object) -> XMLContent:
        proc = cast(JobProcessor, kwargs['proc'])
        # We use 'final' as the primary sort key to make sure that the first
        # row (containing the task name) only collapses if all parameters for
        # that task are final.
        taskParams = {
            task.getName(): sorted(
                (task.isFinal(key), key, value)
                for key, value in task.getParameters().items()
                if not key.startswith('sf.')
                )
            for task in proc.job.getTaskSequence()
            }
        presentation = super().present(taskParams=taskParams, **kwargs)
        if presentation is not None:
            yield presentation

class InputTable(ProductTable):
    label = 'Input'
    showProducers = False
    showConsumers = False
    showColors = False

    def getProducts(self, proc: JobProcessor) -> Sequence[Product]:
        # Create list of inputs in alphabetical order.
        return sorted(proc.job.getInputs())

    def presentCaptionParts(self, **kwargs: object) -> XMLContent:
        proc = cast(JobProcessor, kwargs['proc'])
        numInputs = len(proc.job.getInputs())
        yield 'Job consumes the following %s:' % (
            'input' if numInputs == 1 else f'{numInputs:d} inputs'
            )

class OutputTable(ProductTable):
    label = 'Output'
    showProducers = True
    showConsumers = False
    showColors = True
    widgetId = 'outputTable'
    autoUpdate = True

    def getProducts(self, proc: JobProcessor) -> Sequence[Product]:
        return proc.job.getProduced()

    def presentCaptionParts(self, **kwargs: object) -> XMLContent:
        proc = cast(JobProcessor, kwargs['proc'])
        numOutputs = len(proc.job.getProduced())
        yield 'Job produces the following %s:' % (
            'output' if numOutputs == 1 else f'{numOutputs:d} outputs'
            )

def presentTaskRunner(resourceDB: ResourceDB, runnerId: str) -> XMLContent:
    content: XMLContent
    try:
        runner = resourceDB.getTaskRunner(runnerId)
    except KeyError:
        status = 'lost'
        content = runnerId
    else:
        status = getResourceStatus(runner)
        content = createTaskRunnerDetailsLink(runnerId)
    return cell(class_=status)[ content ]

def presentTaskRunners(resourceDB: ResourceDB,
                       taskLabel: str,
                       runnerIds: Collection[str]
                       ) -> Iterator[XMLContent]:
    first = True
    for runner in sorted(runnerIds):
        if first:
            yield (
                cell(rowspan = len(runnerIds))[ taskLabel ],
                presentTaskRunner(resourceDB, runner)
                )
            first = False
        else:
            yield presentTaskRunner(resourceDB, runner),

class TaskRunnerTable(Table):
    columns = 'Task', 'Task Runners'
    hideWhenEmpty = True
    style = 'nostrong'
    widgetId = 'trSelTable'
    autoUpdate = True

    def presentCaptionParts(self, **kwargs: object) -> XMLContent:
        yield 'The following Task Runners may be used:'

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(JobProcessor, kwargs['proc'])
        resourceDB = proc.resourceDB
        tasks = proc.job.getTaskSequence()
        trsPerTask = 0
        for task in tasks:
            trSet = task.getRunners()
            if trSet:
                trsPerTask += 1
                yield from presentTaskRunners(
                                resourceDB, task.getName(), trSet)
        if trsPerTask < len(tasks):
            taskLabel = 'all tasks' if trsPerTask == 0 else 'other tasks'
            defaultTRs = proc.job.getRunners()
            if defaultTRs:
                yield from presentTaskRunners(
                                resourceDB, taskLabel, defaultTRs)
            elif trsPerTask != 0:
                yield taskLabel, 'any'

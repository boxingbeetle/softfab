# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, Sequence, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import DataTable
from softfab.jobview import CommentPanel, JobsSubTable, presentJobCaption
from softfab.pagelinks import (
    JobIdArgs, TaskIdArgs, createTaskInfoLink, createTaskRunnerDetailsLink
)
from softfab.productlib import Product
from softfab.productview import ProductTable
from softfab.request import Request
from softfab.resourcelib import getTaskRunner
from softfab.resourceview import getResourceStatus
from softfab.tasktables import JobProcessorMixin, JobTaskRunsTable
from softfab.userlib import User, checkPrivilege
from softfab.webgui import Table, Widget, cell, pageLink
from softfab.xmlgen import XMLContent, xhtml


class JobProcessor(JobProcessorMixin, PageProcessor[JobIdArgs]):

    def process(self, req: Request[JobIdArgs], user: User) -> None:
        self.initJob(req)

class SelfJobsTable(JobsSubTable):
    descriptionLink = False
    widgetId = 'selfJobsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc):
        return [ proc.job ]

class TaskRunsTable(JobTaskRunsTable):
    widgetId = 'taskRunsTable'
    autoUpdate = True

    def presentCaptionParts(self, *, proc, **kwargs):
        return presentJobCaption(proc.job)

class ShowReport_GET(FabPage['ShowReport_GET.Processor',
                             'ShowReport_GET.Arguments']):
    icon = 'IconReport'
    description = 'Job'
    children = ['AbortTask', 'Task']

    class Arguments(JobIdArgs):
        pass

    class Processor(JobProcessor):
        pass

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/a')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
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
    columns = 'Task', 'Parameter', 'Value'
    hideWhenEmpty = True

    def presentCaptionParts(self, **kwargs):
        yield 'Job uses the following parameters:'

    def iterRows(self, *, proc, **kwargs):
        jobId = proc.args.jobId
        for task in proc.job.getTaskSequence():
            params = task.getVisibleParameters()
            first = True
            for key, value in sorted(params.items()):
                if first:
                    yield cell(rowspan = len(params))[
                        createTaskInfoLink(jobId, task.getName())
                        ], key, value
                    first = False
                else:
                    yield key, value

    def present(self, **kwargs):
        presentation = super().present(**kwargs)
        if presentation is None:
            message = 'This job contains no non-final parameters. '
        else:
            yield presentation
            message = 'Final parameters are not shown in the table above. '
        yield xhtml.p[
            message,
            'If you follow one of the task name links, you are taken to '
            'the task info page which lists all parameters.'
            ]

class InputTable(ProductTable):
    label = 'Input'
    showProducers = False
    showConsumers = False
    showColors = False

    def getProducts(self, proc: JobProcessor) -> Sequence[Product]:
        # Create list of inputs in alphabetical order.
        return sorted(proc.job.getInputs())

    def presentCaptionParts(self, *, proc, **kwargs):
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

    def presentCaptionParts(self, *, proc, **kwargs):
        numOutputs = len(proc.job.getProduced())
        yield 'Job produces the following %s:' % (
            'output' if numOutputs == 1 else f'{numOutputs:d} outputs'
            )

def presentTaskRunner(runnerId):
    try:
        runner = getTaskRunner(runnerId)
    except KeyError:
        status = 'lost'
        content = runnerId
    else:
        status = getResourceStatus(runner)
        content = createTaskRunnerDetailsLink(runnerId)
    return cell(class_=status)[ content ]

def presentTaskRunners(taskLabel, runnerIds):
    first = True
    for runner in sorted(runnerIds):
        if first:
            yield (
                cell(rowspan = len(runnerIds))[ taskLabel ],
                presentTaskRunner(runner)
                )
            first = False
        else:
            yield presentTaskRunner(runner),

class TaskRunnerTable(Table):
    columns = 'Task', 'Task Runners'
    hideWhenEmpty = True
    style = 'nostrong'
    widgetId = 'trSelTable'
    autoUpdate = True

    def presentCaptionParts(self, **kwargs):
        yield 'The following Task Runners may be used:'

    def iterRows(self, *, proc, **kwargs):
        tasks = proc.job.getTaskSequence()
        trsPerTask = 0
        for task in tasks:
            trSet = task.getRunners()
            if trSet:
                trsPerTask += 1
                yield from presentTaskRunners(task.getName(), trSet)
        if trsPerTask < len(tasks):
            taskLabel = 'all tasks' if trsPerTask == 0 else 'other tasks'
            defaultTRs = proc.job.getRunners()
            if defaultTRs:
                yield from presentTaskRunners(taskLabel, defaultTRs)
            elif trsPerTask != 0:
                yield taskLabel, 'any'

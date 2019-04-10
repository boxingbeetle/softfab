# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.datawidgets import DataTable
from softfab.joblib import jobDB
from softfab.jobview import CommentPanel, JobsSubTable
from softfab.pagelinks import (
    JobIdArgs, TaskIdArgs, createConfigDetailsLink, createTaskInfoLink,
    createTaskRunnerDetailsLink
)
from softfab.productview import ProductTable
from softfab.resourcelib import getTaskRunner, iterTaskRunners
from softfab.resourceview import getResourceStatus
from softfab.tasktables import JobTaskRunsTable
from softfab.userlib import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import Table, Widget, cell, pageLink
from softfab.xmlgen import XMLContent, xhtml


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
        jobId = proc.args.jobId
        numTasks = len(proc.job.getTaskSequence())
        configId = proc.job.getConfigId()
        yield 'Job ', jobId, ' was created from ', (
            'scratch' if configId is None else (
                'configuration ', xhtml.b[ createConfigDetailsLink(configId) ]
                ),
            ' and contains ', str(numTasks), ' ', pluralize('task', numTasks),
            ':'
            )

class ShowReport_GET(FabPage['ShowReport_GET.Processor',
                             'ShowReport_GET.Arguments']):
    icon = 'IconReport'
    description = 'Show Reports'
    children = [ 'AbortTask', 'ExtractionDetails', 'ShowTaskInfo' ]

    class Arguments(JobIdArgs):
        pass

    class Processor(PageProcessor[JobIdArgs]):

        def process(self, req, user):
            jobId = req.args.jobId
            try:
                job = jobDB[jobId]
            except KeyError:
                raise InvalidRequest('No job exists with ID "%s"' % jobId)
            job.updateSummaries(tuple(iterTaskRunners()))
            # pylint: disable=attribute-defined-outside-init
            self.job = job

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
        if not job.hasFinalResult() and (
                job.getRunners() or
                any(task.getRunners() for task in job.iterTasks())
                ):
            yield TaskRunnerTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
        jobId = proc.args.jobId
        job = proc.job
        tasks = job.getTaskSequence()

        yield SelfJobsTable.instance.present(proc=proc)
        yield TaskRunsTable.instance.present(proc=proc)

        if not job.hasFinalResult():
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

        yield CommentPanel(job.comment).present(proc=proc)
        yield InputTable.instance.present(proc=proc)
        yield OutputTable.instance.present(proc=proc)
        yield ParamTable.instance.present(proc=proc)
        if not job.hasFinalResult():
            # Note: We check hasFinalResult instead of isExecutionFinished
            #       because the Task Runner binding applies to extraction too
            #       and often postponed inspection is done on the Factory PC
            #       that ran the task.
            yield TaskRunnerTable.instance.present(proc=proc)

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

    def getProducts(self, proc):
        # Create list of inputs in alphabetical order.
        return sorted(proc.job.getInputs())

    def presentCaptionParts(self, *, proc, **kwargs):
        numInputs = len(proc.job.getInputs())
        yield 'Job consumes the following %s:' % (
            'input' if numInputs == 1 else '%d inputs' % numInputs
            )

class OutputTable(ProductTable):
    label = 'Output'
    showProducers = True
    showConsumers = False
    showColors = True
    widgetId = 'outputTable'
    autoUpdate = True

    def getProducts(self, proc):
        return proc.job.getProduced()

    def presentCaptionParts(self, *, proc, **kwargs):
        numOutputs = len(proc.job.getProduced())
        yield 'Job produces the following %s:' % (
            'output' if numOutputs == 1 else '%d outputs' % numOutputs
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

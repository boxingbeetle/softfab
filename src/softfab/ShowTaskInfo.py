# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from Page import PageProcessor
from frameworklib import frameworkDB
from joblib import jobDB
from pagelinks import (
    TaskIdArgs, createFrameworkDetailsLink, createJobLink,
    createTaskDetailsLink, createTaskHistoryLink, createTaskRunnerDetailsLink
    )
from paramview import ParametersTable
from productview import ProductTable
from projectlib import project
from resourceview import InlineResourcesTable
from selectview import valuesToText
from taskdeflib import taskDefDB
from taskdefview import formatTimeout
from taskrunnerlib import taskRunnerDB
from tasktables import JobTaskRunsTable
from webgui import PropertiesTable
from xmlgen import txt, xhtml

taskParametersTable = ParametersTable('task')

class SelfTaskRunsTable(JobTaskRunsTable):
    taskNameLink = False
    widgetId = 'selfTaskRunsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc):
        return [ proc.task ]

class DetailsTable(PropertiesTable):

    def presentCaptionParts(self, proc, **kwargs):
        taskName = proc.args.taskName
        jobId = proc.args.jobId
        yield 'Task ', (xhtml.b[ taskName ], ' is part of Job: ',
            createJobLink(jobId))

    def iterRows(self, proc, **kwargs):
        task = proc.task
        run = task.getLatestRun()
        taskDef = proc.taskDef
        taskDefId = taskDef.getId()
        frameworkId = taskDef['parent']
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
        yield 'Parameters', taskParametersTable.present(proc=proc, **kwargs)

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

class InputTable(ProductTable):
    label = 'Input'
    hideWhenEmpty = False
    showProducers = True
    showConsumers = False
    showColors = True
    widgetId = 'inputTable'
    autoUpdate = True

    def presentCaptionParts(self, proc, **kwargs):
        taskName = proc.args.taskName
        yield 'Task ', xhtml.b[ taskName ], ' consumes the following inputs:'

    def getProducts(self, proc):
        job = proc.job
        task = proc.task
        # Create list of inputs in alphabetical order.
        return [
            job.getProduct(prodName)
            for prodName in sorted(task.getInputs())
            ]

class OutputTable(ProductTable):
    label = 'Output'
    hideWhenEmpty = False
    showProducers = False
    showConsumers = True
    showColors = True
    widgetId = 'outputTable'
    autoUpdate = True

    def presentCaptionParts(self, proc, **kwargs):
        taskName = proc.args.taskName
        yield 'Task ', xhtml.b[ taskName ], ' produces the following outputs:'

    def getProducts(self, proc):
        job = proc.job
        task = proc.task
        # Create list of outputs in alphabetical order.
        return [
            job.getProduct(prodName)
            for prodName in sorted(task.getOutputs())
            ]

    def filterProducers(self, proc, producers):
        # Only show producer if it is our task.
        taskName = proc.args.taskName
        if taskName in producers:
            yield taskName

class ShowTaskInfo(FabPage):
    icon = 'IconReport'
    description = 'Show Task Info'

    class Arguments(TaskIdArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            jobId = req.args.jobId
            taskName = req.args.taskName

            job = jobDB.get(jobId)
            task = None
            taskDef = None
            if job is not None:
                task = job.getTask(taskName)
                if task is not None:
                    taskDef = task.getDef()
                    job.updateSummaries(taskRunnerDB)

            # pylint: disable=attribute-defined-outside-init
            self.job = job
            self.task = task
            self.taskDef = taskDef

    def checkAccess(self, req):
        req.checkPrivilege('j/a')

    def iterWidgets(self, proc):
        yield SelfTaskRunsTable
        yield InputTable
        yield OutputTable

    def iterDataTables(self, proc):
        yield SelfTaskRunsTable.instance

    def presentContent(self, proc):
        job = proc.job
        task = proc.task
        jobId = proc.args.jobId
        taskName = proc.args.taskName

        if job is None:
            yield (
                xhtml.h2[ 'Invalid job ID' ],
                xhtml.p[
                    'There is no job with ID ', xhtml.b[ jobId ]
                    ]
                )
            # No parent link, since it would point to an invalid job as well.
            return
        if task is None:
            yield (
                xhtml.h2[ 'Invalid task name' ],
                xhtml.p[
                    'There is no task named ', xhtml.b[ taskName ],
                    ' in this job.'
                    ],
                self.backToParent(proc.req)
                )
            return

        taskName = task.getName()
        yield SelfTaskRunsTable.instance.present(proc=proc)
        yield DetailsTable.instance.present(proc=proc)
        yield InputTable.instance.present(proc=proc)
        yield OutputTable.instance.present(proc=proc)
        yield xhtml.p[ createTaskHistoryLink(taskName) ]

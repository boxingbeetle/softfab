# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from Page import PageProcessor
from config import enableSecurity
from connection import ConnectionStatus
from pagelinks import (
    ResourceIdArgs, TaskRunnerIdArgs, createJobLink, createTaskLink
    )
from resourceview import getResourceStatus, presentCapabilities
from restypelib import taskRunnerResourceTypeName
from taskrunnerlib import taskRunnerDB
from timeview import formatDuration, formatTime
from webgui import Column, Table, pageLink, row
from xmlgen import xhtml

class TaskRunnerDetails(FabPage):
    icon = 'TaskRunStat1'
    description = 'Task Runner Details'

    class Arguments(TaskRunnerIdArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            runnerId = req.args.runnerId
            # pylint: disable=attribute-defined-outside-init
            self.taskRunner = taskRunnerDB.get(runnerId)

    def checkAccess(self, req):
        req.checkPrivilege('tr/a')

    def iterWidgets(self, proc):
        yield DetailsTable

    def presentContent(self, proc):
        taskRunner = proc.taskRunner
        if taskRunner is None:
            yield xhtml.p[
                'Task Runner ', xhtml.b[ proc.args.runnerId ],
                ' does not exist.'
                ]
            return

        yield xhtml.h2[
            'Details / ',
            pageLink('TaskRunnerHistory', TaskRunnerIdArgs.subset(proc.args))[
                'History'
                ],
            ' of Task Runner ', xhtml.b[ proc.args.runnerId ], ':'
            ]
        yield DetailsTable.instance.present(proc=proc)
        yield xhtml.p[xhtml.br.join(self.__presentLinks(taskRunner))]

    def __presentLinks(self, taskRunner):
        args = ResourceIdArgs(id = taskRunner.getId())
        yield pageLink('TaskRunnerEdit', args)[
            'Edit properties of this Task Runner'
            ]
        if taskRunner.getConnectionStatus() is ConnectionStatus.LOST:
            yield pageLink('DelTaskRunnerRecord', args)[
                'Delete record of this Task Runner'
                ]

class DetailsTable(Table):
    widgetId = 'detailsTable'
    autoUpdate = True
    columns = Column('Property', cellStyle = 'nobreak'), 'Value'

    def iterRows(self, proc, **kwargs):
        runner = proc.taskRunner
        yield 'Description', runner.description
        yield 'Version', runner['runnerVersion']
        yield 'Host', runner['host']
        yield 'Target', runner['target']
        yield 'Capabilities', presentCapabilities(
            runner.capabilities,
            taskRunnerResourceTypeName
            )
        yield 'Time since last sync', formatDuration(runner['lastSync'])
        run = runner.getRun()
        yield 'Current job', (
            '-' if run is None else createJobLink(run['jobId'])
            )
        yield 'Current task', createTaskLink(runner)
        yield 'Duration', formatDuration(run.getDuration() if run else None)
        status = getResourceStatus(runner)
        yield row(class_ = status)[ 'Status', status ]
        yield 'Exit when idle', 'yes' if runner.shouldExit() else 'no'
        yield 'Suspended', 'yes' if runner.isSuspended() else 'no'
        if enableSecurity:
            user = runner.getChangedUser()
            if user is None:
                # Note: It is possible this TR was never suspended.
                yield 'Last suspended/resumed by', 'unknown'
            else:
                if runner.isSuspended():
                    label = 'Last suspended by'
                else:
                    label = 'Last resumed by'
                yield label, '%s at %s' % (
                    user, formatTime(runner.getChangedTime())
                    )

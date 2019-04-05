# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.connection import ConnectionStatus
from softfab.pagelinks import (
    ResourceIdArgs, TaskRunnerIdArgs, createJobLink, createTaskLink
)
from softfab.resourceview import getResourceStatus, presentCapabilities
from softfab.restypelib import taskRunnerResourceTypeName
from softfab.taskrunnerlib import taskRunnerDB
from softfab.timeview import formatDuration, formatTime
from softfab.userlib import User, checkPrivilege
from softfab.webgui import Column, Table, Widget, pageLink, row
from softfab.xmlgen import XMLContent, xhtml


class TaskRunnerDetails_GET(FabPage['TaskRunnerDetails_GET.Processor',
                                    'TaskRunnerDetails_GET.Arguments']):
    icon = 'TaskRunStat1'
    description = 'Task Runner Details'

    class Arguments(TaskRunnerIdArgs):
        pass

    class Processor(PageProcessor[TaskRunnerIdArgs]):

        def process(self, req, user):
            runnerId = req.args.runnerId
            # pylint: disable=attribute-defined-outside-init
            self.taskRunner = taskRunnerDB.get(runnerId)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'tr/a')

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        yield DetailsTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
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

    def iterRows(self, *, proc, **kwargs):
        runner = proc.taskRunner
        yield 'Description', runner.description
        yield 'Version', runner['runnerVersion']
        yield 'Host', runner['host']
        yield 'Targets', presentCapabilities(
            runner.targets,
            taskRunnerResourceTypeName
            )
        yield 'Other capabilities', presentCapabilities(
            runner.capabilities - runner.targets,
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

        label = 'Last suspended' if runner.isSuspended() else 'Last resumed'
        changedTime = runner.getChangedTime()
        if changedTime == 0:
            changeDesc = 'never'
        else:
            changeDesc = 'by %s at %s' % (
                runner.getChangedUser() or 'unknown',
                formatTime(changedTime)
                )
        yield label, changeDesc

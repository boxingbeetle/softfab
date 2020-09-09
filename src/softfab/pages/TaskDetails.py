# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Iterable, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError
from softfab.RecordDelete import DeleteArgs
from softfab.configlib import ConfigDB
from softfab.pagelinks import (
    TaskDefIdArgs, createConfigDetailsLink, createFrameworkDetailsLink,
    createTaskHistoryLink
)
from softfab.paramview import ParametersTable
from softfab.request import Request
from softfab.resourceview import InlineResourcesTable
from softfab.taskdeflib import TaskDefDB
from softfab.taskdefview import configsUsingTaskDef, formatTimeout
from softfab.users import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import PropertiesTable, pageLink
from softfab.xmlgen import XML, XMLContent, xhtml

taskDefParametersTable = ParametersTable('taskDef')

class DetailsTable(PropertiesTable):

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(TaskDetails_GET.Processor, kwargs['proc'])
        taskDef = proc.taskDef
        configs = proc.configs

        def formatConfigs(configIds: Iterable[str]) -> XMLContent:
            return xhtml.br.join(
                createConfigDetailsLink(proc.configDB, configId)
                for configId in sorted(configIds)
                )

        yield 'Title', taskDef['title']
        yield 'Description', taskDef['description']
        frameworkId = taskDef.frameworkId
        yield 'Framework', (
            '-'
            if frameworkId is None
            else createFrameworkDetailsLink(frameworkId)
            )
        yield 'Timeout', formatTimeout(taskDef.timeoutMins)
        yield 'Parameters', taskDefParametersTable.present(**kwargs)
        yield 'Resources', InlineResourcesTable.instance.present(
            claim=taskDef.getFramework().resourceClaim.merge(
                taskDef.resourceClaim
                ),
            **kwargs
            )
        yield 'Configurations', formatConfigs(configs)

class TaskDetails_GET(FabPage['TaskDetails_GET.Processor',
                              'TaskDetails_GET.Arguments']):
    icon = 'TaskDef2'
    description = 'Task Definition Details'

    class Arguments(TaskDefIdArgs):
        pass

    class Processor(PageProcessor[TaskDefIdArgs]):

        taskDefDB: ClassVar[TaskDefDB]
        configDB: ClassVar[ConfigDB]

        async def process(self,
                          req: Request[TaskDefIdArgs],
                          user: User
                          ) -> None:
            taskDefId = req.args.id

            try:
                taskDef = self.taskDefDB[taskDefId]
            except KeyError:
                raise PresentableError(xhtml[
                    'Task Definition ', xhtml.b[ taskDefId ], ' does not exist.'
                    ])

            # pylint: disable=attribute-defined-outside-init
            self.taskDef = taskDef
            self.configs = list(configsUsingTaskDef(self.configDB, taskDefId))

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'td/a')

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(TaskDetails_GET.Processor, kwargs['proc'])
        taskDefId = proc.args.id
        configs = proc.configs

        yield xhtml.h3[
            'Details of task definition ', xhtml.b[ taskDefId ], ':'
            ]
        yield DetailsTable.instance.present(**kwargs)
        yield xhtml.p[ createTaskHistoryLink(taskDefId) ]
        numConfigs = len(configs)
        yield xhtml.p[
            pageLink('TaskEdit', proc.args)[ 'Edit this task definition' ],
            xhtml.br,
            ( 'Delete this task definition: not possible, because it is '
              'currently being used by ', str(numConfigs), ' ',
              pluralize('configuration', numConfigs), '.'
            ) if configs else pageLink(
                'TaskDelete', DeleteArgs(id = taskDefId)
                )[ 'Delete this task definition' ]
            ]

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield xhtml.p[ message ]

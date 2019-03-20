# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.RecordDelete import DeleteArgs
from softfab.pagelinks import (
    TaskDefIdArgs, createConfigDetailsLink, createFrameworkDetailsLink,
    createTaskHistoryLink
)
from softfab.paramview import ParametersTable
from softfab.projectlib import project
from softfab.resourceview import InlineResourcesTable
from softfab.selectview import valuesToText
from softfab.taskdeflib import taskDefDB
from softfab.taskdefview import configsUsingTaskDef, formatTimeout
from softfab.userlib import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import PropertiesTable, pageLink
from softfab.xmlgen import XMLContent, xhtml

taskDefParametersTable = ParametersTable('taskDef')

class DetailsTable(PropertiesTable):

    def iterRows(self, *, proc, **kwargs):
        taskDef = proc.taskDef
        configs = proc.configs

        def formatConfigs(configIds):
            return xhtml.br.join(
                createConfigDetailsLink(configId)
                for configId in sorted(configIds)
                )

        yield 'Title', taskDef['title']
        yield 'Description', taskDef['description']
        yield 'Framework', createFrameworkDetailsLink(taskDef['parent'])
        yield 'Timeout', formatTimeout(taskDef.timeoutMins)
        # Check if requirements are enabled in project settings
        if project['reqtag']:
            yield 'Requirements', valuesToText(taskDef.getTagValues('sf.req'))
        yield 'Parameters', taskDefParametersTable.present(proc=proc, **kwargs)
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

        def process(self, req, user):
            # pylint: disable=attribute-defined-outside-init
            self.taskDef = taskDefDB.get(req.args.id)
            self.configs = list(configsUsingTaskDef(req.args.id))

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'td/a')

    def presentContent(self, proc: Processor) -> XMLContent:
        taskDef = proc.taskDef
        taskDefId = proc.args.id
        configs = proc.configs

        if taskDef is None:
            yield xhtml.p[
                'Task Definition ', xhtml.b[ taskDefId ], ' does not exist.'
                ]
            return
        yield xhtml.h2[
            'Details of task definition ', xhtml.b[ taskDefId ], ':'
            ]
        yield DetailsTable.instance.present(proc=proc)
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

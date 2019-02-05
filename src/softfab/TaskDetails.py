# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from Page import PageProcessor
from RecordDelete import DeleteArgs
from pagelinks import (
    TaskDefIdArgs, createConfigDetailsLink, createFrameworkDetailsLink,
    createTaskHistoryLink
    )
from paramview import ParametersTable
from projectlib import project
from resourceview import InlineResourcesTable
from selectview import valuesToText
from taskdeflib import taskDefDB
from taskdefview import configsUsingTaskDef, formatTimeout
from utils import pluralize
from webgui import PropertiesTable, pageLink
from xmlgen import xhtml

taskDefParametersTable = ParametersTable('taskDef')

class DetailsTable(PropertiesTable):

    def iterRows(self, proc, **kwargs):
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

class TaskDetails(FabPage):
    icon = 'TaskDef2'
    description = 'Task Definition Details'

    class Arguments(TaskDefIdArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            # pylint: disable=attribute-defined-outside-init
            self.taskDef = taskDefDB.get(req.args.id)
            self.configs = list(configsUsingTaskDef(req.args.id))

    def checkAccess(self, req):
        req.checkPrivilege('td/a')

    def presentContent(self, proc):
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
            xhtml.br.join((
                pageLink('TaskEdit', proc.args)[ 'Edit this task definition' ],
                ( 'Delete this task definition: not possible, because it is '
                  'currently being used by ', str(numConfigs), ' ',
                  pluralize('configuration', numConfigs), '.'
                  ) if configs else pageLink(
                    'TaskDelete', DeleteArgs(id = taskDefId)
                    )[ 'Delete this task definition' ]
                ))
            ]

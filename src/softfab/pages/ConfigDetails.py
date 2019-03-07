# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.RecordDelete import DeleteArgs
from softfab.configlib import configDB
from softfab.graphview import GraphPageMixin, GraphPanel, createExecutionGraph
from softfab.jobview import CommentPanel
from softfab.pagelinks import (
    ConfigIdArgs, createTaskDetailsLink, createTaskRunnerDetailsLink
    )
from softfab.productview import formatLocator
from softfab.projectlib import project
from softfab.schedulelib import scheduleDB
from softfab.schedulerefs import createScheduleDetailsLink
from softfab.selectview import TagArgs
from softfab.utils import encodeURL, pluralize
from softfab.webgui import (
    PresenterFunction, Table, cell, decoration, pageLink, unorderedList
    )
from softfab.xmlgen import txt, xhtml

# Note:
# The following pieces of information are not included in this page:
# - Task Runner selection
# - task priorities
# - target
# - owner
# This was done both to keep the page simple and to save implementation effort.
# However, if some of that info is missed by the users, maybe we will have to
# introduce it later.

class TagsTable(Table):
    columns = 'Key', 'Values'
    hideWhenEmpty = True

    def iterRows(self, proc, **kwargs):
        config = proc.config
        for key in project.getTagKeys():
            values = config.getTagValues(key)
            if values:
                yield key, txt(', ').join(
                    pageLink(
                        'LoadExecute',
                        TagArgs(tagkey = key, tagvalue = value)
                        )[ value ]
                    for value in sorted(values)
                    )

decoratedTagsTable = decoration[
    xhtml.p[ 'Configuration is tagged as follows:' ],
    TagsTable.instance
    ]

class TasksTable(Table):
    columns = 'Task', 'Parameter', 'Value'

    def iterRows(self, proc, **kwargs):
        tasksByName = sorted(
            ( task.getName(), task )
            for task in proc.config.getTasks()
            )
        for taskName, task in tasksByName:
            taskLink = createTaskDetailsLink(taskName)
            params = task.getVisibleParameters()
            first = True
            for key, value in sorted(params.items()):
                if first:
                    yield cell(rowspan = len(params))[taskLink], key, value
                    first = False
                else:
                    yield key, value
            if first:
                yield taskLink, '-', '-'

class InputTable(Table):
    hideWhenEmpty = True

    def iterColumns(self, proc, **kwargs):
        yield 'Input'
        yield 'Locator'
        if proc.config.hasLocalInputs():
            yield 'Local at'

    def iterRows(self, proc, **kwargs):
        config = proc.config
        hasLocal = config.hasLocalInputs()
        for product in sorted(config.getInputs()):
            cells = [
                product['name'],
                formatLocator(product, product['locator'], True)
                ]
            if hasLocal:
                cells.append(
                    createTaskRunnerDetailsLink(
                        ( product.getLocalAt() or '?' )
                        if product.isLocal() else None
                        )
                    )
            yield cells

decoratedInputTable = decoration[
    xhtml.p[ 'Configuration consumes the following inputs:' ],
    InputTable.instance
    ]

decoratedConflictsList = decoration[
    xhtml.p(class_ = 'notice')[
        'The following problems exist with the stored inputs:'
        ],
    PresenterFunction(lambda proc, **kwargs:
        unorderedList[
            proc.config.iterInputConflicts()
            ].present(proc=proc, **kwargs)
        )
    ]

class SchedulesTable(Table):
    columns = 'Schedule',
    hideWhenEmpty = True

    def iterRows(self, proc, **kwargs):
        for scheduleId in sorted(proc.scheduleIds):
            yield createScheduleDetailsLink(scheduleId),

decoratedSchedulesTable = decoration[
    xhtml.p[ 'Configuration can be instantiated by the following schedules:' ],
    SchedulesTable.instance
    ]

class ConfigDetails_GET(GraphPageMixin, FabPage['ConfigDetails_GET.Processor']):
    icon = 'IconExec'
    description = 'Configuration Details'

    class Arguments(ConfigIdArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            configId = req.args.configId
            config = configDB.get(configId)

            if config is None:
                graph = None
                scheduleIds = None
            else:
                frameworkIds = []
                productIds = set()
                for task in config.getTasks():
                    framework = task.getFramework()
                    if not framework.getId() in frameworkIds:
                        frameworkIds.append(framework.getId())
                    productIds |= framework.getInputs()
                    productIds |= framework.getOutputs()
                graph = createExecutionGraph(
                    'graph',
                    productIds,
                    frameworkIds,
                    req.getSubPath() is not None
                    )
                scheduleIds = tuple(
                    scheduleId
                    for scheduleId, schedule in scheduleDB.items()
                    if configId in schedule.getMatchingConfigIds()
                    )

            # pylint: disable=attribute-defined-outside-init
            self.config = config
            self.graph = graph
            self.scheduleIds = scheduleIds

    def checkAccess(self, req):
        req.checkPrivilege('c/a')

    def presentContent(self, proc):
        config = proc.config
        configId = proc.args.configId
        if config is None:
            yield xhtml.p[
                'Configuration ', xhtml.b[ configId ], ' does not exist.'
                ]
            return

        yield xhtml.h2[ 'Details of configuration ', xhtml.b[ configId ], ':' ]
        yield xhtml.p[
            'Execution graph of frameworks and products in this configuration:'
            ]
        yield GraphPanel.instance.present(proc=proc, graph=proc.graph)
        yield decoratedTagsTable.present(proc=proc)
        yield CommentPanel(config.comment).present(proc=proc)
        yield decoratedInputTable.present(proc=proc)
        yield decoratedConflictsList.present(proc=proc)
        yield xhtml.p[ 'Configuration contains the following tasks:' ]
        yield TasksTable.instance.present(proc=proc)
        yield decoratedSchedulesTable.present(proc=proc)
        numSchedules = len(proc.scheduleIds)
        yield xhtml.p[
            xhtml.br.join((
                ( pageLink('FastExecute', proc.args)[
                    'Execute this configuration'
                    ], ' (confirmation only)' ),
                ( xhtml.a(
                    href = 'Execute?' + encodeURL(( ('config', configId), ))
                    )[ 'Load this configuration' ],
                    ' (provide inputs and parameters)' ),
                ( xhtml.a(
                    href = 'ReportIndex?' + encodeURL(( ('desc', configId), ))
                    )[ 'Show history of this configuration' ] ),
                ( xhtml.a(
                    href = 'Execute?' + encodeURL((
                        ('config', configId), ('step', 'edit')
                        ))
                    )[ 'Edit this configuration' ] ),
                ( 'Delete this configuration: not possible, because it is'
                  ' currently being used by ', str(numSchedules), ' ',
                  pluralize('schedule', numSchedules), '.'
                  ) if proc.scheduleIds else pageLink(
                    'DelJobConfig', DeleteArgs(id = configId)
                    )[ 'Delete this configuration' ]
                ))
            ]

# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Iterable, Iterator, List, Set, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError
from softfab.RecordDelete import DeleteArgs
from softfab.configlib import ConfigDB
from softfab.frameworklib import FrameworkDB
from softfab.graphview import ExecutionGraphBuilder, GraphPageMixin, GraphPanel
from softfab.jobview import CommentPanel
from softfab.pagelinks import (
    ConfigIdArgs, createTaskDetailsLink, createTaskRunnerDetailsLink
)
from softfab.productdeflib import ProductDefDB
from softfab.productlib import Product
from softfab.productview import formatLocator
from softfab.request import Request
from softfab.restypeview import createTargetLink
from softfab.schedulelib import ScheduleDB
from softfab.schedulerefs import createScheduleDetailsLink
from softfab.selectview import TagArgs
from softfab.userlib import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import (
    Column, PresenterFunction, Table, cell, decoration, pageLink, unorderedList
)
from softfab.xmlgen import XML, XMLContent, xhtml

# Note:
# The following pieces of information are not included in this page:
# - Task Runner selection
# - task priorities
# - owner
# This was done both to keep the page simple and to save implementation effort.
# However, if some of that info is missed by the users, maybe we will have to
# introduce it later.

class TagsTable(Table):
    columns = 'Key', 'Values'
    hideWhenEmpty = True

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast('ConfigDetails_GET.Processor', kwargs['proc'])
        config = proc.config
        for key in proc.project.getTagKeys():
            values = config.tags.getTagValues(key)
            if values:
                yield key, xhtml[', '].join(
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

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast('ConfigDetails_GET.Processor', kwargs['proc'])
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

    def iterColumns(self, **kwargs: object) -> Iterator[Column]:
        proc = cast(ConfigDetails_GET.Processor, kwargs['proc'])
        yield Column('Input')
        yield Column('Locator')
        if proc.config.hasLocalInputs():
            yield Column('Local at')

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast('ConfigDetails_GET.Processor', kwargs['proc'])
        config = proc.config
        hasLocal = config.hasLocalInputs()
        for product in sorted(config.getInputs()):
            cells = [
                product.getName(),
                # TODO: Input objects are not actually instances of Product.
                #       This is a candidate for refactoring; see TODOs in
                #       docstring of configlib.Input.
                formatLocator(cast(Product, product),
                              product.getLocator(), True)
                ]
            if hasLocal:
                cells.append(
                    createTaskRunnerDetailsLink(
                        ( product.getLocalAt() or '?' )
                        if product.isLocal() else None
                        )
                    )
            yield cells

def presentTargets(**kwargs: object) -> XMLContent:
    proc = cast(ConfigDetails_GET.Processor, kwargs['proc'])
    targets = proc.config.targets
    if targets:
        yield xhtml.p[
            'Configuration will create jobs for the following targets:'
            ]
        yield unorderedList[(
            createTargetLink(target) for target in sorted(targets)
            )].present()
    elif proc.project.getTargets():
        yield xhtml.p[
            'Configuration will create jobs with ', xhtml.b['no target'],
            ' requirements.'
            ]

decoratedInputTable = decoration[
    xhtml.p[ 'Configuration consumes the following inputs:' ],
    InputTable.instance
    ]

def presentInputConflicts(**kwargs: object) -> XMLContent:
    proc = cast('ConfigDetails_GET.Processor', kwargs['proc'])
    return unorderedList[
        proc.config.iterInputConflicts()
        ].present(**kwargs)

decoratedConflictsList = decoration[
    xhtml.p(class_ = 'notice')[
        'The following problems exist with the stored inputs:'
        ],
    PresenterFunction(presentInputConflicts)
    ]

class SchedulesTable(Table):
    columns = 'Schedule',
    hideWhenEmpty = True

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast('ConfigDetails_GET.Processor', kwargs['proc'])
        for scheduleId in sorted(proc.scheduleIds):
            yield createScheduleDetailsLink(scheduleId),

decoratedSchedulesTable = decoration[
    xhtml.p[ 'Configuration can be instantiated by the following schedules:' ],
    SchedulesTable.instance
    ]

class ConfigDetails_GET(
        GraphPageMixin,
        FabPage['ConfigDetails_GET.Processor', 'ConfigDetails_GET.Arguments']
        ):
    icon = 'IconExec'
    description = 'Configuration Details'

    class Arguments(ConfigIdArgs):
        pass

    class Processor(PageProcessor['ConfigDetails_GET.Arguments']):

        configDB: ClassVar[ConfigDB]
        frameworkDB: ClassVar[FrameworkDB]
        productDefDB: ClassVar[ProductDefDB]
        scheduleDB: ClassVar[ScheduleDB]

        async def process(self,
                          req: Request['ConfigDetails_GET.Arguments'],
                          user: User
                          ) -> None:
            configId = req.args.configId
            configDB = self.configDB
            frameworkDB = self.frameworkDB
            productDefDB = self.productDefDB
            scheduleDB = self.scheduleDB

            try:
                config = configDB[configId]
            except KeyError:
                raise PresentableError(xhtml[
                    'Configuration ', xhtml.b[ configId ], ' does not exist.'
                    ])

            frameworkIds: List[str] = []
            productIds: Set[str] = set()
            for task in config.getTasks():
                framework = task.getFramework()
                if not framework.getId() in frameworkIds:
                    frameworkIds.append(framework.getId())
                productIds |= framework.getInputs()
                productIds |= framework.getOutputs()
            graphBuilder = ExecutionGraphBuilder(
                'graph',
                products=(productDefDB[pid] for pid in productIds),
                frameworks=(frameworkDB[fid] for fid in frameworkIds),
                )
            scheduleIds = tuple(
                scheduleId
                for scheduleId, schedule in scheduleDB.items()
                if configId in schedule.getMatchingConfigIds(configDB)
                )

            # pylint: disable=attribute-defined-outside-init
            self.config = config
            self.graph = graphBuilder
            self.scheduleIds = scheduleIds

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'c/a')

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ConfigDetails_GET.Processor, kwargs['proc'])
        config = proc.config
        configId = proc.args.configId
        yield xhtml.h3[ 'Details of configuration ', xhtml.b[ configId ], ':' ]
        yield xhtml.p[
            'Execution graph of frameworks and products in this configuration:'
            ]
        yield GraphPanel.instance.present(graph=proc.graph, **kwargs)
        yield decoratedTagsTable.present(**kwargs)
        yield CommentPanel(config.comment).present(**kwargs)
        yield presentTargets(**kwargs)
        yield decoratedInputTable.present(**kwargs)
        yield decoratedConflictsList.present(**kwargs)
        yield xhtml.p[ 'Configuration contains the following tasks:' ]
        yield TasksTable.instance.present(**kwargs)
        yield decoratedSchedulesTable.present(**kwargs)
        yield xhtml.p[ xhtml.br.join(self.iterLinks(proc)) ]

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield xhtml.p[ message ]

    def iterLinks(self, proc: Processor) -> Iterable[XMLContent]:
        yield pageLink('FastExecute', proc.args)[
            'Execute this configuration'
            ], ' (confirmation only)'
        configId = proc.args.configId
        yield pageLink('Execute', config=configId)[
            'Load this configuration'
            ], ' (provide inputs and parameters)'
        yield pageLink('ReportIndex', desc=configId)[
            'Show history of this configuration'
            ]
        yield pageLink('Execute', config=configId, step='edit')[
            'Edit this configuration'
            ]
        if proc.scheduleIds:
            numSchedules = len(proc.scheduleIds)
            yield (
                'Delete this configuration: not possible, because it is'
                ' currently being used by ', str(numSchedules), ' ',
                pluralize('schedule', numSchedules), '.'
                )
        else:
            yield pageLink('DelJobConfig', DeleteArgs(id=configId))[
                'Delete this configuration'
                ]

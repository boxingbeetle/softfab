# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterable, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError
from softfab.RecordDelete import DeleteArgs
from softfab.frameworklib import frameworkDB
from softfab.frameworkview import taskDefsUsingFramework
from softfab.graphview import GraphPageMixin, GraphPanel, createExecutionGraph
from softfab.pagelinks import (
    FrameworkIdArgs, createProductDetailsLink, createTaskDetailsLink
)
from softfab.paramview import ParametersTable
from softfab.request import Request
from softfab.resourceview import InlineResourcesTable
from softfab.userlib import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import PropertiesTable, hgroup, pageLink
from softfab.xmlgen import XML, XMLContent, xhtml

# Note: We use "taskDef" here to refer to instances of TaskDefBase,
#       mostly frameworks. This was done in anticipation of replacing
#       the fixed two-level inheritance with flexible inheritance.

frameworkParametersTable = ParametersTable('taskDef')

def formatProducts(products: Iterable[str]) -> XMLContent:
    return xhtml.br.join(
        createProductDetailsLink(productDefId)
        for productDefId in sorted(products)
        )

def formatTaskDefs(children: Iterable[str]) -> XMLContent:
    return xhtml.br.join(
        createTaskDetailsLink(taskDefId)
        for taskDefId in sorted(children)
        )

class DetailsTable(PropertiesTable):

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(FrameworkDetails_GET.Processor, kwargs['proc'])
        taskDef = proc.taskDef
        yield 'Wrapper', taskDef['wrapper']
        yield 'Inputs', formatProducts(taskDef.getInputs())
        yield 'Outputs', formatProducts(taskDef.getOutputs())
        yield 'Parameters', frameworkParametersTable.present(**kwargs)
        yield 'Resources', InlineResourcesTable.instance.present(
            claim=taskDef.resourceClaim, **kwargs
            )
        yield 'Task Definitions', formatTaskDefs(proc.children)

class FrameworkDetails_GET(
        GraphPageMixin,
        FabPage['FrameworkDetails_GET.Processor',
                'FrameworkDetails_GET.Arguments']
        ):
    icon = 'Framework1'
    description = 'Framework Details'

    class Arguments(FrameworkIdArgs):
        pass

    class Processor(PageProcessor[FrameworkIdArgs]):

        def process(self, req: Request[FrameworkIdArgs], user: User) -> None:
            frameworkId = req.args.id
            try:
                framework = frameworkDB[frameworkId]
            except KeyError:
                raise PresentableError(xhtml[
                    'Framework ', xhtml.b[ frameworkId ], ' does not exist.'
                    ])
            taskDefs = list(taskDefsUsingFramework(frameworkId))

            graph = createExecutionGraph(
                'graph',
                framework.getInputs() | framework.getOutputs(),
                [ frameworkId ],
                req.getSubPath() is not None
                )

            # pylint: disable=attribute-defined-outside-init
            self.taskDef = framework
            self.children = taskDefs
            self.graph = graph

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'fd/a')

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(FrameworkDetails_GET.Processor, kwargs['proc'])
        frameworkId = proc.args.id
        children = proc.children
        numChildren = len(children)
        deleteFramework = (
            'Delete this framework: not possible, '
            'because it is currently being used by ', str(numChildren), ' ',
            pluralize('task definition', numChildren), '.'
            ) if children else pageLink(
                'FrameworkDelete', DeleteArgs(id = frameworkId)
                )[ 'Delete this framework' ]

        yield xhtml.h3[ 'Details of framework ', xhtml.b[ frameworkId ], ':' ]
        yield hgroup[
            DetailsTable.instance,
            GraphPanel.instance.present(graph=proc.graph, **kwargs)
            ].present(**kwargs)
        yield xhtml.p[
            pageLink('FrameworkEdit', proc.args)[ 'Edit this framework' ],
            xhtml.br,
            deleteFramework
            ]

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield xhtml.p[ message ]

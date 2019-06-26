# SPDX-License-Identifier: BSD-3-Clause

'''
The Design page containing the execution graph(s).
'''

from typing import Sized, Tuple, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.graphview import (
    GraphPageMixin, GraphPanel, canCreateGraphs, createExecutionGraph,
    createLegend, iterConnectedExecutionGraphs
)
from softfab.pageargs import PageArgs, StrArg
from softfab.request import Request
from softfab.userlib import User, checkPrivilege
from softfab.webgui import docLink, pageLink
from softfab.xmlgen import XMLContent, xhtml


class Design_GET(
        GraphPageMixin,
        FabPage['Design_GET.Processor', 'Design_GET.Arguments']
        ):
    icon = 'IconDesign'
    description = 'Design'
    children = [
        'ProductIndex', 'FrameworkIndex', 'TaskIndex', 'ResTypeIndex'
        ]

    class Arguments(PageArgs):
        show = StrArg('no')

    class Processor(PageProcessor['Design_GET.Arguments']):

        def process(self,
                    req: Request['Design_GET.Arguments'],
                    user: User
                    ) -> None:
            orphanProducts = set()
            orphanFrameworks = set()
            nonTrivialGraphs = []
            for productIds, frameworkIds in iterConnectedExecutionGraphs():
                numProducts = len(productIds)
                numFrameworks = len(frameworkIds)
                if numProducts == 1 and numFrameworks == 0:
                    orphanProducts.add(productIds.pop())
                elif numProducts == 0 and numFrameworks == 1:
                    orphanFrameworks.add(frameworkIds.pop())
                else:
                    nonTrivialGraphs.append((productIds, frameworkIds))
            def keyFunc(productAndFrameworkIds: Tuple[Sized, ...]) -> int:
                return sum(len(ids) for ids in productAndFrameworkIds)
            graphNodes = sorted(
                nonTrivialGraphs,
                key = keyFunc,
                reverse = True
                )
            if orphanFrameworks:
                graphNodes.append((set(), orphanFrameworks))
            if orphanProducts:
                graphNodes.append((orphanProducts, set()))
            export = req.getSubPath() is not None
            graphs = []
            if req.args.show == 'yes':
                for index, (productIds, frameworkIds) in enumerate(graphNodes):
                    graphs.append( createExecutionGraph( 'graph%d' % index,
                        productIds, frameworkIds, export)
                        )
            graphs.append(createLegend(export))
            # pylint: disable=attribute-defined-outside-init
            self.graphs = graphs
            self.show = req.args.show

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'fd/a')
        checkPrivilege(user, 'pd/a')

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(Design_GET.Processor, kwargs['proc'])
        show = proc.args.show
        if show == 'yes':
            if len(proc.graphs) == 1: # only containing the Legend
                yield xhtml.p[
                    'This factory has no product and framework definitions yet.'
                    ]
                yield xhtml.p[
                    "Please start designing the factory "
                    'by adding new products and frameworks. '
                    'Select the "Products" or "Frameworks" button '
                    'from the navigation bar above.'
                    ]
            else:
                yield xhtml.p[
                    'Execution graph(s) of the products and frameworks:'
                    ]

        if canCreateGraphs:
            if show == 'yes':
                for index, graph in enumerate(proc.graphs):
                    if index == len(proc.graphs) - 1:
                        yield xhtml.h2[ 'Legend' ]
                    yield GraphPanel.instance.present(graph=graph, **kwargs)
            else:
                yield xhtml.p[
                    pageLink('Design', show='yes')[ 'Execution Graph(s)' ],
                    ': Show the graph(s) of the products and frameworks and '
                    'their interconnections.'
                    ]
                yield xhtml.hr
                descriptions = [
                    ( 'Products', 'ProductIndex',
                        'Lists all products, create new products or '
                        'edit existing products.'
                        ),
                    ( 'Frameworks', 'FrameworkIndex',
                        'Lists all frameworks, create new frameworks or '
                        'edit existing frameworks.'
                        ),
                    ( 'Task Definitions', 'TaskIndex',
                        'Lists all task definitions, '
                        'create new task definitions or '
                        'edit existing task definitions.'
                        ),
                    ( 'Resources Types', 'ResTypeIndex',
                        'Lists all resources types, create new resource types '
                        'or edit existing resource types.'
                        )
                    ]
                yield xhtml.dl(class_='toc')[(
                    (xhtml.dt[xhtml.a(href=url)[name]], xhtml.dd[descr])
                    for name, url, descr in descriptions
                    )]
        else:
            yield xhtml.p(class_ = 'notice')[
                'Graph creation is not available because the server '
                'does not have "pygraphviz" installed.'
                ]
        yield xhtml.p[
            'For help please read the documentation about the ',
            docLink('/concepts/exegraph/')[
                'Execution Graph'
                ], ', ',
            docLink('/concepts/taskdefs/')[
                'Framework and Task Definitions'
                ], ' or ',
            docLink('/start/user_manual/#resources')[ 'Resources' ], '.'
            ]

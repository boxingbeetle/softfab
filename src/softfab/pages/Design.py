# SPDX-License-Identifier: BSD-3-Clause

'''
The Design page containing the execution graph(s).
'''

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.graphview import (
    GraphPageMixin, GraphPanel, canCreateGraphs, createExecutionGraph,
    createLegend, iterConnectedExecutionGraphs
)
from softfab.pageargs import PageArgs, StrArg
from softfab.userlib import checkPrivilege
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

    class Processor(PageProcessor):

        def process(self, req):
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
            graphNodes = sorted(
                nonTrivialGraphs,
                key = lambda productAndFrameworkIds: sum(
                    len(ids) for ids in productAndFrameworkIds
                    ),
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

    def checkAccess(self, user):
        checkPrivilege(user, 'fd/a')
        checkPrivilege(user, 'pd/a')

    def presentContent(self, proc: Processor) -> XMLContent:
        show = proc.args.show
        if show == 'yes':
            if len(proc.graphs) == 1: # only containing the Legend
                yield xhtml.p[
                    'This factory has no Product and Framework definitions yet.'
                    ]
                yield xhtml.p[
                    "Please start designing the factory "
                    'by adding new Products and Frameworks. '
                    'Select the "Products" or "Frameworks" button '
                    'from the navigation bar above.'
                    ]
            else:
                yield xhtml.p[
                    'Execution graph(s) of the Frameworks and Products:'
                    ]

        if canCreateGraphs:
            if show == 'yes':
                for index, graph in enumerate(proc.graphs):
                    if index == len(proc.graphs) - 1:
                        yield xhtml.h2[ 'Legend' ]
                    yield GraphPanel.instance.present(proc=proc, graph=graph)
            else:
                yield xhtml.p[
                    pageLink('Design', show='yes')[ 'Execution Graph(s)' ],
                    ': Show the graph(s) of the Frameworks and Products and '
                    'their interconnections.'
                    ]
                yield xhtml.hr
                descriptions = [
                    ( 'Products',
                        'Lists all Products, Create new Products or '
                        'Edit existing Products.'
                        ),
                    ( 'Frameworks',
                        'Lists all Frameworks, Create new Frameworks or '
                        'Edit existing Frameworks.'
                        ),
                    ( 'Task Definitions',
                        'Lists all Task Definitions, '
                        'Create new Task Definitions or '
                        'Edit existing Task Definitions.'
                        ),
                    ( 'Resources',
                        'Lists all Resources, Create new Resources and '
                        'Resource Types or Edit existing Resources.'
                        )
                    ]
                yield xhtml.dl[(
                    (xhtml.dt[name], xhtml.dd[descr])
                    for name, descr in descriptions
                    )]
        else:
            yield xhtml.p(class_ = 'notice')[
                'Graph creation is not available because the server '
                'does not have "pygraphviz" installed.'
                ]
        yield xhtml.p[
            'For help please read the documentation about the ',
            docLink('/introduction/execution-graph/')[ 'Execution Graph' ], ', ',
            docLink('/introduction/framework-and-task-definitions/')[
                'Framework and Task Definitions'
                ], ' or ',
            docLink('/reference/user-manual/#resources')[ 'Resources' ], '.'
            ]

# SPDX-License-Identifier: BSD-3-Clause

'''
The Design page containing the execution graph(s).
'''

from typing import ClassVar, Sized, Tuple, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.frameworklib import FrameworkDB
from softfab.graphview import (
    ExecutionGraphBuilder, GraphPageMixin, GraphPanel,
    iterConnectedExecutionGraphs, legendBuilder
)
from softfab.productdeflib import ProductDefDB
from softfab.request import Request
from softfab.users import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import docLink
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

    class Processor(PageProcessor['Design_GET.Arguments']):

        frameworkDB: ClassVar[FrameworkDB]
        productDefDB: ClassVar[ProductDefDB]

        async def process(self,
                          req: Request['Design_GET.Arguments'],
                          user: User
                          ) -> None:
            frameworkDB = self.frameworkDB
            productDefDB = self.productDefDB

            orphanProducts = set()
            orphanFrameworks = set()
            nonTrivialGraphs = []
            for productIds, frameworkIds in iterConnectedExecutionGraphs(
                                                    frameworkDB, productDefDB):
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
            graphBuilders = [
                ExecutionGraphBuilder(
                    f'graph{index:d}',
                    products=(productDefDB[pid] for pid in productIds),
                    frameworks=(frameworkDB[fid] for fid in frameworkIds)
                    )
                for index, (productIds, frameworkIds) in enumerate(graphNodes)
                ]
            graphBuilders.append(legendBuilder)
            # pylint: disable=attribute-defined-outside-init
            self.graphs = graphBuilders

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'fd/a')
        checkPrivilege(user, 'pd/a')

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(Design_GET.Processor, kwargs['proc'])
        graphs = proc.graphs[:-1]
        legend = proc.graphs[-1]

        if graphs:
            yield xhtml.p[
                f"Execution {pluralize('graph', len(graphs))} of "
                f"the products and frameworks:"
                ]
            yield xhtml.div(class_='hgroup wrap')[(
                GraphPanel.instance.present(graph=graph, **kwargs)
                for graph in graphs
                )].present(**kwargs)
        else:
            yield xhtml.p[
                'This factory has no product and framework definitions yet.'
                ]
            yield xhtml.p[
                "Please start designing the factory "
                'by adding new products and frameworks. '
                'Select the "Products" or "Frameworks" button '
                'from the navigation bar above.'
                ]

        yield xhtml.h2[ 'Legend' ]
        yield GraphPanel.instance.present(graph=legend, **kwargs)

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

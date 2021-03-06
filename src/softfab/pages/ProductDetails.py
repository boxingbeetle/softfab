# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Iterable, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError
from softfab.RecordDelete import DeleteArgs
from softfab.frameworklib import FrameworkDB
from softfab.graphview import ExecutionGraphBuilder, GraphPageMixin, GraphPanel
from softfab.pagelinks import ProductDefIdArgs, createFrameworkDetailsLink
from softfab.productdeflib import ProductDefDB
from softfab.request import Request
from softfab.users import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import PropertiesTable, pageLink
from softfab.xmlgen import XML, XMLContent, xhtml


class DetailsTable(PropertiesTable):

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(ProductDetails_GET.Processor, kwargs['proc'])
        productDef = proc.productDef
        producers = proc.producers
        consumers = proc.consumers

        def formatFrameworks(frameworks: Iterable[str]) -> XMLContent:
            return xhtml.br.join(
                createFrameworkDetailsLink(frameworkId)
                for frameworkId in sorted(frameworks)
                )

        yield 'Type', productDef['type']
        yield 'Local', 'yes' if productDef.isLocal() else 'no'
        yield 'Combined', 'yes' if productDef.isCombined() else 'no'
        yield 'Producers', formatFrameworks(producers)
        yield 'Consumers', formatFrameworks(consumers)

class ProductDetails_GET(
        GraphPageMixin,
        FabPage['ProductDetails_GET.Processor', 'ProductDetails_GET.Arguments']
        ):
    icon = 'Product1'
    description = 'Product Details'

    class Arguments(ProductDefIdArgs):
        pass

    class Processor(PageProcessor[ProductDefIdArgs]):

        frameworkDB: ClassVar[FrameworkDB]
        productDefDB: ClassVar[ProductDefDB]

        async def process(self,
                          req: Request[ProductDefIdArgs],
                          user: User
                          ) -> None:
            productDefId = req.args.id
            frameworkDB = self.frameworkDB
            productDefDB = self.productDefDB

            try:
                productDef = productDefDB[productDefId]
            except KeyError:
                raise PresentableError(xhtml[
                    'Product ', xhtml.b[ productDefId ], ' does not exist.'
                    ])

            producers = []
            consumers = []
            for frameworkId, framework in frameworkDB.items():
                if productDefId in framework.getInputs():
                    consumers.append(frameworkId)
                if productDefId in framework.getOutputs():
                    producers.append(frameworkId)

            graphBuilder = ExecutionGraphBuilder(
                'graph',
                products=[productDef],
                frameworks=(frameworkDB[fid] for fid in producers + consumers),
                )

            # pylint: disable=attribute-defined-outside-init
            self.productDef = productDef
            self.producers = producers
            self.consumers = consumers
            self.graph = graphBuilder

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'pd/a')

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ProductDetails_GET.Processor, kwargs['proc'])
        productDefId = proc.args.id
        producers = proc.producers
        consumers = proc.consumers

        numProducers = len(producers)
        numConsumers = len(consumers)
        deleteProduct = ( 'Delete this product: '
            'not possible, because it is currently being used by ',
            str(numProducers), ' ', pluralize('producer', numProducers),
            ' and ',
            str(numConsumers), ' ', pluralize('consumer', numConsumers), '.'
            ) if producers or consumers else pageLink(
                'ProductDelete', DeleteArgs(id = productDefId)
                )[ 'Delete this Product' ]

        yield xhtml.h3[ 'Details of product ', xhtml.b[ productDefId ], ':' ]
        yield xhtml.div(class_='hgroup wrap')[
            DetailsTable.instance,
            GraphPanel.instance
            ].present(graph=proc.graph, **kwargs)
        yield xhtml.p[
            pageLink('ProductEdit', proc.args)[ 'Edit this product' ],
            xhtml.br,
            deleteProduct
            ]

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield xhtml.p[ message ]

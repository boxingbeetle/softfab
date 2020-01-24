# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterable, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError
from softfab.RecordDelete import DeleteArgs
from softfab.frameworklib import frameworkDB
from softfab.graphview import GraphPageMixin, GraphPanel, createExecutionGraph
from softfab.pagelinks import ProductDefIdArgs, createFrameworkDetailsLink
from softfab.productdeflib import productDefDB
from softfab.request import Request
from softfab.userlib import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import PropertiesTable, hgroup, pageLink
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

        def process(self, req: Request[ProductDefIdArgs], user: User) -> None:
            productDefId = req.args.id

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

            graph = createExecutionGraph(
                'graph',
                [ productDefId ],
                producers + consumers,
                req.getSubPath() is not None
                )

            # pylint: disable=attribute-defined-outside-init
            self.productDef = productDef
            self.producers = producers
            self.consumers = consumers
            self.graph = graph

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
        yield hgroup[
            DetailsTable.instance,
            GraphPanel.instance.present(graph=proc.graph, **kwargs)
            ].present(**kwargs)
        yield xhtml.p[
            pageLink('ProductEdit', proc.args)[ 'Edit this product' ],
            xhtml.br,
            deleteProduct
            ]

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield xhtml.p[ message ]

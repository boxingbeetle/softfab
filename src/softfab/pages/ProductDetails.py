# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.RecordDelete import DeleteArgs
from softfab.frameworklib import frameworkDB
from softfab.graphview import GraphPageMixin, GraphPanel, createExecutionGraph
from softfab.pagelinks import ProductDefIdArgs, createFrameworkDetailsLink
from softfab.productdeflib import productDefDB
from softfab.userlib import checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import PropertiesTable, hgroup, pageLink
from softfab.xmlgen import XMLContent, xhtml


class DetailsTable(PropertiesTable):

    def iterRows(self, *, proc, **kwargs):
        productDef = proc.productDef
        producers = proc.producers
        consumers = proc.consumers

        def formatFrameworks(frameworks):
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

    class Processor(PageProcessor):

        def process(self, req):
            productDefId = req.args.id

            productDef = productDefDB.get(productDefId)

            producers = []
            consumers = []
            for frameworkId, framework in frameworkDB.items():
                if productDefId in framework.getInputs():
                    consumers.append(frameworkId)
                if productDefId in framework.getOutputs():
                    producers.append(frameworkId)

            graph = None if productDef is None else createExecutionGraph(
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

    def checkAccess(self, user):
        checkPrivilege(user, 'pd/a')

    def presentContent(self, proc: Processor) -> XMLContent:
        productDef = proc.productDef
        productDefId = proc.args.id
        producers = proc.producers
        consumers = proc.consumers

        if productDef is None:
            yield xhtml.p[
                'Product ', xhtml.b[ productDefId ], ' does not exist.'
                ]
            return

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

        yield xhtml.h2[ 'Details of product ', xhtml.b[ productDefId ], ':' ]
        yield hgroup[
            DetailsTable.instance,
            GraphPanel.instance.present(proc=proc, graph=proc.graph)
            ].present(proc=proc)
        yield xhtml.p[
            pageLink('ProductEdit', proc.args)[ 'Edit this product' ],
            xhtml.br,
            deleteProduct
            ]

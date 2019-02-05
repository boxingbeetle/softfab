# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from Page import PageProcessor
from RecordDelete import DeleteArgs
from frameworklib import frameworkDB
from graphview import GraphPageMixin, GraphPanel, createExecutionGraph
from pagelinks import ProductDefIdArgs, createFrameworkDetailsLink
from productdeflib import productDefDB
from utils import pluralize
from webgui import PropertiesTable, hgroup, pageLink
from xmlgen import xhtml

class DetailsTable(PropertiesTable):

    def iterRows(self, proc, **kwargs):
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

class ProductDetails(GraphPageMixin, FabPage):
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

    def checkAccess(self, req):
        req.checkPrivilege('pd/a')

    def presentContent(self, proc):
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
            xhtml.br.join((
                pageLink('ProductEdit', proc.args)[ 'Edit this product' ],
                deleteProduct
                ))
            ]

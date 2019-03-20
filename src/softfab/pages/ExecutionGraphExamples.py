# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import FabResource, PageProcessor
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.frameworklib import Framework
from softfab.graphview import ExecutionGraphBuilder, GraphPageMixin
from softfab.productdeflib import ProductDef, ProductType
from softfab.userlib import User
from softfab.webgui import Table
from softfab.xmlgen import XMLContent, xhtml


class TaskGraphBuilder(ExecutionGraphBuilder):

    def populate(self): # pylint: disable=arguments-differ
        self.addFramework(Framework.create('build', (), ()))

class ProductGraphBuilder(ExecutionGraphBuilder):

    def populate(self): # pylint: disable=arguments-differ
        self.addProduct(ProductDef.create('binary'))

class DependencyGraphBuilder(ExecutionGraphBuilder):

    def populate(self): # pylint: disable=arguments-differ
        self.addProduct(ProductDef.create('binary'))
        self.addFramework(Framework.create('build', (), ('binary',)))
        self.addFramework(Framework.create('test', ('binary',), ()))

class TokenProductGraphBuilder(ExecutionGraphBuilder):

    def populate(self): # pylint: disable=arguments-differ
        self.addProduct(
            ProductDef.create('app_installed', prodType = ProductType.TOKEN)
            )

class CombinedProductGraphBuilder(ExecutionGraphBuilder):

    def populate(self): # pylint: disable=arguments-differ
        self.addProduct(ProductDef.create('coverage_data', combined = True))

class ExecutionGraphExamples_GET(
        GraphPageMixin,
        UIPage['ExecutionGraphExamples_GET.Processor'],
        FabResource['FabResource.Arguments',
                    'ExecutionGraphExamples_GET.Processor']
        ):
    authenticator = NoAuthPage

    class Processor(PageProcessor):

        def process(self, req, user):
            export = False
            graphs = [
                cls.build(name, export, False)
                for name, cls in (
                    ( 'task', TaskGraphBuilder ),
                    ( 'product', ProductGraphBuilder ),
                    ( 'dependency', DependencyGraphBuilder ),
                    ( 'token', TokenProductGraphBuilder ),
                    ( 'combined', CombinedProductGraphBuilder ),
                    )
                ]

            # pylint: disable=attribute-defined-outside-init
            self.graphs = graphs

    def pageTitle(self, proc: Processor) -> str:
        return 'Execution Graphs'

    def checkAccess(self, user: User) -> None:
        pass

    def presentContent(self, proc: Processor) -> XMLContent:
        for graph in proc.graphs:
            yield PNGPanel.instance.present(
                proc=proc,
                imagePath='%s.png' % graph.getName()
                )

class PNGPanel(Table):
    '''Presents an PNG image on a panel, with the same frame and background as
    tables.
    '''
    columns = None,
    hideWhenEmpty = True

    def iterRows(self, *, proc, imagePath, **kwargs):
        baseName = imagePath[imagePath.rfind('/') + 1 : ]
        description = baseName.rsplit('.', 1)[0]
        yield xhtml.img(
            src=proc.subItemRelURL(imagePath),
            alt=description,
            ),

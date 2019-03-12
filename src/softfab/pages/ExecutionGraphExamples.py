# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import FabResource, PageProcessor
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.frameworklib import Framework
from softfab.graphview import ExecutionGraphBuilder, GraphPageMixin
from softfab.productdeflib import ProductDef, ProductType
from softfab.webgui import Table
from softfab.xmlgen import xhtml

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
        FabResource['ExecutionGraphExamples_GET.Processor']
        ):
    authenticator = NoAuthPage

    class Processor(PageProcessor):

        def process(self, req):
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

    def checkAccess(self, req):
        pass

    def presentContent(self, proc):
        for graph in proc.graphs:
            proc.imagePath = '%s.png' % graph.getName()
            yield PNGPanel.instance.present(proc=proc)

class PNGPanel(Table):
    '''Presents an PNG image on a panel, with the same frame and background as
    tables.
    The image should be specified using a subitem path in "proc.imagePath",
    or it can be None, in which case the panel is not presented.
    '''
    columns = None,
    hideWhenEmpty = True

    def iterRows(self, *, proc, **kwargs):
        imagePath = proc.imagePath
        if imagePath is not None:
            baseName = imagePath[imagePath.rfind('/') + 1 : ]
            description = baseName.rsplit('.', 1)[0]
            yield xhtml.img(
                src = proc.subItemRelURL(imagePath),
                alt = description,
                ),

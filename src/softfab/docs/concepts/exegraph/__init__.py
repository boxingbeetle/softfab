# SPDX-License-Identifier: BSD-3-Clause

from softfab.docserve import piHandler
from softfab.frameworklib import Framework
from softfab.graphview import ExecutionGraphBuilder, GraphPanel
from softfab.productdeflib import ProductDef, ProductType
from softfab.xmlgen import XMLContent, xhtml

button = 'Graph'
children = ()

class TaskGraphBuilder(ExecutionGraphBuilder):

    def populate(self, **kwargs: object) -> None:
        self.addFramework(Framework.create('build', (), ()))

class ProductGraphBuilder(ExecutionGraphBuilder):

    def populate(self, **kwargs: object) -> None:
        self.addProduct(ProductDef.create('binary'))

class DependencyGraphBuilder(ExecutionGraphBuilder):

    def populate(self, **kwargs: object) -> None:
        self.addProduct(ProductDef.create('binary'))
        self.addFramework(Framework.create('build', (), ('binary',)))
        self.addFramework(Framework.create('test', ('binary',), ()))

class TokenProductGraphBuilder(ExecutionGraphBuilder):

    def populate(self, **kwargs: object) -> None:
        self.addProduct(
            ProductDef.create('app_installed', prodType=ProductType.TOKEN)
            )

class CombinedProductGraphBuilder(ExecutionGraphBuilder):

    def populate(self): # pylint: disable=arguments-differ
        self.addProduct(ProductDef.create('coverage_data', combined = True))

graphBuilders = dict(
    task=TaskGraphBuilder,
    product=ProductGraphBuilder,
    dependency=DependencyGraphBuilder,
    token=TokenProductGraphBuilder,
    combined=CombinedProductGraphBuilder,
    )

@piHandler
def graph(arg: str) -> XMLContent:
    return GraphPanel.instance.present(
        graph=graphBuilders[arg].build(arg, False, False)
        )

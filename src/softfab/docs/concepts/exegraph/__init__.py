# SPDX-License-Identifier: BSD-3-Clause

from softfab.docserve import piHandler
from softfab.frameworklib import Framework
from softfab.graphview import ExecutionGraphBuilder, GraphPanel
from softfab.productdeflib import ProductDef, ProductType
from softfab.xmlgen import XMLContent

button = 'Graph'
children = ()
icon = 'IconDesign'

graphBuilders = {
    builder.name: builder
    for builder in (
        ExecutionGraphBuilder(
            'task',
            frameworks=(
                Framework.create('build', (), ()),
                )
            ),
        ExecutionGraphBuilder(
            'product',
            products=(
                ProductDef.create('binary'),
                )
            ),
        ExecutionGraphBuilder(
            'dependency',
            products=(
                ProductDef.create('binary'),
                ),
            frameworks=(
                Framework.create('build', (), ('binary',)),
                Framework.create('test', ('binary',), ())
                ),
            ),
        ExecutionGraphBuilder(
            'token',
            products=(
                ProductDef.create('app_installed', prodType=ProductType.TOKEN),
                ),
            ),
        ExecutionGraphBuilder(
            'combined',
            products=(
                ProductDef.create('coverage_data', combined=True),
                ),
            ),
        )
    }

docGraphPanel = GraphPanel(links=False)

@piHandler
def graph(arg: str) -> XMLContent:
    return docGraphPanel.present(graph=graphBuilders[arg])

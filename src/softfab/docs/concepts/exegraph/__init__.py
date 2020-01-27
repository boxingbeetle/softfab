# SPDX-License-Identifier: BSD-3-Clause

from softfab.docserve import piHandler
from softfab.frameworklib import Framework
from softfab.graphview import ExecutionGraphBuilder
from softfab.productdeflib import ProductDef, ProductType
from softfab.xmlgen import XMLContent, xhtml

button = 'Graph'
children = ()
icon = 'IconDesign'

graphBuilders = {
    builder.name: builder
    for builder in (
        ExecutionGraphBuilder(
            'task',
            links=False,
            frameworks=(
                Framework.create('build', (), ()),
                ),
            ),
        ExecutionGraphBuilder(
            'product',
            links=False,
            products=(
                ProductDef.create('binary'),
                ),
            ),
        ExecutionGraphBuilder(
            'dependency',
            links=False,
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
            links=False,
            products=(
                ProductDef.create('app_installed', prodType=ProductType.TOKEN),
                ),
            ),
        ExecutionGraphBuilder(
            'combined',
            links=False,
            products=(
                ProductDef.create('coverage_data', combined=True),
                ),
            ),
        )
    }

@piHandler
def graph(arg: str) -> XMLContent:
    svg = graphBuilders[arg].build(export=False).toSVG()
    return xhtml.div(class_='graph')[ xhtml.div[ svg ] ]

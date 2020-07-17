# SPDX-License-Identifier: BSD-3-Clause

from functools import partial
from typing import Dict

from twisted.internet.defer import DeferredList, ensureDeferred

from softfab.docserve import piHandler
from softfab.frameworklib import Framework
from softfab.graphview import ExecutionGraphBuilder
from softfab.productdeflib import ProductDef, ProductType
from softfab.webgui import PresenterFunction
from softfab.xmlgen import XML, XMLContent, xhtml

button = 'Graph'
children = ()
icon = 'IconDesign'

graphBuilders = (
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

graphRenders: Dict[str, XML] = {}

async def renderGraph(builder: ExecutionGraphBuilder) -> None:
    consumer = await builder.build(export=False).toSVG()
    graphRenders[builder.name] = xhtml[ consumer.takeSVG() ]

async def process() -> None:
    deferreds = [
        ensureDeferred(renderGraph(builder))
        for builder in graphBuilders
        if builder.name not in graphRenders
        ]
    if deferreds:
        await DeferredList(deferreds)

def presentGraph( # pylint: disable=unused-argument
                 name: str, **kwargs: object
                 ) -> XMLContent:
    try:
        svg = graphRenders[name]
    except KeyError:
        svg = xhtml.span(class_='notice')['Graph rendering failed']
    return xhtml.div(class_='graph')[ xhtml.div[ svg ] ]

@piHandler
def graph(arg: str) -> XMLContent:
    return PresenterFunction(partial(presentGraph, name=arg))

# SPDX-License-Identifier: BSD-3-Clause

from functools import partial
from typing import Dict, Optional

from twisted.internet.defer import Deferred, DeferredList

from softfab.docserve import piHandler
from softfab.frameworklib import Framework
from softfab.graphview import ExecutionGraphBuilder
from softfab.productdeflib import ProductDef, ProductType
from softfab.webgui import PresenterFunction
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

graphRenders: Dict[str, XMLContent] = {}

def process() -> Optional[Deferred]:
    deferreds = []
    for name, builder in graphBuilders.items():
        if name not in graphRenders:
            d = builder.build(export=False).toSVG()
            d.addCallback(partial(graphRenders.__setitem__, name))
            deferreds.append(d)
    if deferreds:
        return DeferredList(deferreds)
    else:
        return None

def presentGraph(name: str, **kwargs: object) -> XMLContent:
    try:
        svg = graphRenders[name]
    except KeyError:
        svg = xhtml.span(class_='notice')['Graph rendering failed']
    return xhtml.div(class_='graph')[ xhtml.div[ svg ] ]

@piHandler
def graph(arg: str) -> XMLContent:
    return PresenterFunction(partial(presentGraph, name=arg))

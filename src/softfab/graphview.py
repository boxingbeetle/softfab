# SPDX-License-Identifier: BSD-3-Clause

'''
Builds the execution graphs by using AGraph from the pygraphviz module.
'''

from enum import Enum
from typing import Iterable, Iterator, Optional, Set, Tuple, cast
from xml.etree import ElementTree
import logging
import re

from softfab.Page import PageProcessor, Responder
from softfab.frameworklib import Framework, frameworkDB
from softfab.pagelinks import (
    createFrameworkDetailsURL, createProductDetailsURL
)
from softfab.productdeflib import ProductDef, ProductType, productDefDB
from softfab.response import Response
from softfab.setcalc import UnionFind
from softfab.svglib import SVGPanel, svgNSPrefix
from softfab.xmlgen import XMLContent, txt, xhtml

try:
    from pygraphviz import AGraph
except ImportError:
    canCreateGraphs = False
else:
    canCreateGraphs = True


class GraphFormat(Enum):

    def __init__(self, ext: str, description: str, mediaType: str):
        self.ext = ext
        self.description = description
        self.mediaType = mediaType

    PNG = ('png', 'PNG image', 'image/png')
    SVG = ('svg', 'SVG image', 'image/svg+xml; charset=UTF-8')
    DOT = ('dot', 'GraphViz dot file', 'application/x-graphviz; charset=UTF-8')

# Note: We have multiple instances of "except Exception:" in the
#       code because pygraphviz does not document in its API what
#       exceptions it can raise. Rather than risking catching too
#       little, especially as new versions might raise different
#       exceptions, we catch everything except exit exceptions.

_defaultEdgeAttrib = dict(
    color = 'black:black',
    )
_defaultNodeAttrib = dict(
    fillcolor = 'white',
    fontname = 'Helvetica',
    fontsize = '10',
    height = '0.4',
    style = 'filled',
    )
_defaultGraphAttrib = dict(
    quantum = '0.05',
    rankdir = 'TB',
    ranksep = '0.6 equally',
    )

def iterConnectedExecutionGraphs() -> Iterator[Tuple[Set[str], Set[str]]]:
    '''Returns a collection of (weakly) connected execution graphs.
    For each execution graph, the collection contains a pair with the products
    and frameworks in that connected graph.
    '''
    unionFind: UnionFind[Tuple[str, str]] = UnionFind()

    # Add all products.
    for productId in productDefDB.keys():
        unionFind.add(('prod', productId))

    # Add all frameworks and unite set via produced and consumed products.
    for frameworkId, framework in frameworkDB.items():
        frameworkNodeId = ('fw', frameworkId)
        unionFind.add(frameworkNodeId)
        for productId in framework.getInputs() | framework.getOutputs():
            unionFind.unite(frameworkNodeId, ('prod', productId))

    # Separate products from frameworks.
    for members in unionFind.iterSets():
        productIds = set()
        frameworkIds = set()
        for nodeType, recordId in members:
            if nodeType == 'prod':
                productIds.add(recordId)
            else:
                assert nodeType == 'fw'
                frameworkIds.add(recordId)
        yield productIds, frameworkIds

class Graph:
    '''Wrapper around GraphViz graphs.
    Use a GraphBuilder subclass to construct graphs.
    '''

    def __init__(self, name: str, graph: Optional['AGraph']):
        self.__name = name
        self.__graph = graph

    def getName(self) -> str:
        return self.__name

    def export(self, fmt: GraphFormat) -> Optional[str]:
        '''Renders this graph in the given format.
        Returns the rendered graph data, or None if rendering failed.
        '''
        graph = self.__graph
        if graph is None:
            return None
        try:
            if fmt is GraphFormat.DOT:
                return graph.string()
            elif fmt is GraphFormat.SVG:
                svgElement = self.toSVG()
                if svgElement is None:
                    return None
                return ElementTree.tostring(svgElement, 'utf-8')
            else:
                return graph.draw(format=fmt.ext, prog='dot')
        except Exception:
            logging.exception(
                'Execution graph export failed'
                )
            return None

    def toSVG(self) -> Optional[ElementTree.Element]:
        '''Renders this graph as SVG image and cleans up the resulting SVG.
        If rendering fails, the error is logged and None is returned.
        '''
        graph = self.__graph
        if graph is None:
            return None

        try:
            # Note: This catches exceptions from the rendering process
            svgGraph: str = graph.draw(format='svg', prog='dot')
        except Exception:
            logging.exception(
                'Execution graph rendering (pygraphviz) failed'
                )
            return None

        try:
            # Note: This catches exceptions from the XML parser in
            #       case the generated XML is invalid.
            # ElementTree generates XML (it also adds namespace prefixes)
            svgElement = ElementTree.fromstring( svgGraph )
        except ElementTree.ParseError:
            logging.exception(
                'Generated XML (from svgGraph) is invalid'
                )
            return None

        # Remove <title> elements to reduce output size.
        # It seems only Opera renders these at all (as tool tips). For nodes
        # the title is the same as the text, so not useful at all; for edges
        # the title mentions the nodes it connects, but that is obvious
        # for most graphs.
        svgTitleTag = svgNSPrefix + 'title'
        for group in svgElement.iter(svgNSPrefix + 'g'):
            for title in group.findall(svgTitleTag):
                group.remove(title)

        return svgElement

class GraphBuilder:
    '''Wrapper around GraphViz graphs that are under construction.
    '''

    def __init__(self, graph: 'AGraph', export: bool, links: bool):
        '''Creates a graph.
        Iff "export" is True, the graph is optimized for use outside of the
        Control Center (mailing, printing).
        '''
        self._graph = graph
        self._export = export
        self._links = links

    def populate(self, **kwargs: object) -> None:
        raise NotImplementedError

    @classmethod
    def build(cls,
              name: str, export: bool, links: bool, **kwargs: object
              ) -> Graph:
        '''Creates an empty graph, wraps it in a builder and calls the
        builder's populate() function with the keyword arguments.
        Any errors are logged and not propagated.
        '''

        if not canCreateGraphs:
            return Graph(name, None)

        try:
            graph = AGraph(directed=True, strict=True, id=name)
            graph.node_attr.update(_defaultNodeAttrib)
            graph.edge_attr.update(_defaultEdgeAttrib)
            graph.graph_attr.update(_defaultGraphAttrib)
            graph.graph_attr.update(bgcolor=('white' if export
                                                else 'transparent'))
            builder = cls(graph, export, links)
            builder.populate(**kwargs)
            return Graph(name, graph)
        except Exception:
            logging.exception(
                'Execution graph creation (pygraphviz) failed'
                )
            return Graph(name, None)

class ExecutionGraphBuilder(GraphBuilder):

    def populate(self, **kwargs: object) -> None:
        for product in cast(Iterable[ProductDef], kwargs['products']):
            self.addProduct(product)
        for framework in cast(Iterable[Framework], kwargs['frameworks']):
            self.addFramework(framework)

    def addProduct(self, productDef: ProductDef) -> None:
        '''Add a node for the given product to this graph.
           Specify node attribs if product is a token and/or combined product
        '''
        productId = productDef.getId()
        nodeAttrib = dict(
            label = productId,
            shape = 'box',
            peripheries = '2' if productDef.isCombined() else '1',
            )
        if productDef['type'] is ProductType.TOKEN:
            nodeAttrib['style'] = _defaultNodeAttrib['style'] + ',dashed'
        if self._links:
            nodeAttrib['URL'] = createProductDetailsURL(productId)

        productNodeId = 'prod.' + productId
        graph = self._graph
        assert graph is not None
        if not graph.has_node(productNodeId):
            graph.add_node(productNodeId, **nodeAttrib)

    def addFramework(self, framework: Framework) -> None:
        '''Add a node for the given framework to this graph.
        Also adds edges between the framework to all previously added products
        that are an input or output of this framework.
        Pre-condition: make sure products are added first!
        '''
        frameworkId = framework.getId()
        nodeAttrib = dict(
            label = frameworkId,
            shape = 'oval',
            )

        if self._links:
            nodeAttrib['URL'] = createFrameworkDetailsURL(frameworkId)

        frameworkNodeId = 'fw.' + frameworkId
        if not self._graph.has_node(frameworkNodeId):
            self._graph.add_node(frameworkNodeId, **nodeAttrib)

        for inputDefId in framework.getInputs():
            inputProductNodeId = 'prod.' + inputDefId
            if self._graph.has_node(inputProductNodeId):
                self._graph.add_edge(inputProductNodeId, frameworkNodeId)

        for outputDefId in framework.getOutputs():
            outputProductNodeId = 'prod.' + outputDefId
            if self._graph.has_node(outputProductNodeId):
                self._graph.add_edge(frameworkNodeId, outputProductNodeId)

def createExecutionGraph(name: str,
                         productIds: Iterable[str],
                         frameworkIds: Iterable[str],
                         export: bool
                         ) -> Graph:
    products = [productDefDB[productId] for productId in productIds]
    frameworks = [frameworkDB[frameworkId] for frameworkId in frameworkIds]
    return ExecutionGraphBuilder.build(
        name, export, not export, products=products, frameworks=frameworks
        )

def createLegend(export: bool) -> Graph:
    products = (
        ProductDef.create('product'),
        ProductDef.create('combined-product', combined=True),
        ProductDef.create('token-product', prodType=ProductType.TOKEN)
        )
    frameworks = (
        Framework.create('framework', (), ()),
        )
    return ExecutionGraphBuilder.build(
        'legend', export, False, products=products, frameworks=frameworks
        )


class GraphPanel(SVGPanel):
    '''Presents a graph on a panel, with the same frame and background as
    tables. The graph should be passed to the present method as "graph".
    '''

    def present(self, **kwargs: object) -> XMLContent:
        graph = cast(Graph, kwargs['graph'])
        return super().present(svgElement=graph.toSVG(), **kwargs)

    def presentFooter(self, **kwargs: object) -> XMLContent:
        proc = cast(Optional[PageProcessor], kwargs.get('proc'))
        if proc is None:
            return None
        graph = cast(Graph, kwargs['graph'])
        return xhtml.div(class_ = 'export')[
            'export: ', txt(', ').join(
                xhtml.a(
                    href = proc.subItemRelURL(
                        f'{graph.getName()}.{fmt.ext}'
                        ),
                    title = fmt.description,
                    )[ fmt.ext ]
                for fmt in GraphFormat
                )
            ]

class _GraphResponder(Responder):

    def __init__(self, graph: Graph, fileName: str, fmt: GraphFormat):
        Responder.__init__(self)
        self.__graph = graph
        self.__fileName = fileName
        self.__format = fmt

    def respond(self, response: Response) -> None:
        fmt = self.__format
        response.setHeader('Content-Type', fmt.mediaType)
        response.setFileName(f'{self.__fileName}.{fmt.ext}')
        response.write(self.__graph.export(fmt))

class GraphPageMixin:
    __reGraphPath = re.compile(r'(\w+)\.(\w+)')

    def getResponder(self,
                     path: Optional[str],
                     proc: PageProcessor
                     ) -> Responder:
        if path is None:
            return super().getResponder(path, proc) # type: ignore
        match = self.__reGraphPath.match(path)
        if match is None:
            raise KeyError("Subitem path is not of the form 'file.ext'")
        name, formatStr = match.groups()
        try:
            graph = self.__getGraph(proc, name)
        except KeyError as ex:
            raise KeyError(f'Unknown graph "{name}"') from ex
        try:
            fmt = GraphFormat[formatStr.upper()]
        except ValueError as ex:
            raise KeyError(f'Unknown file format "{formatStr}"') from ex
        return _GraphResponder(graph, name, fmt)

    def __getGraph(self, proc: PageProcessor, name: str) -> Graph:
        if hasattr(proc, 'graphs'):
            graphs: Optional[Iterable[Graph]] = getattr(proc, 'graphs')
            if graphs is None:
                graphs = ()
        elif hasattr(proc, 'graph'):
            graph: Optional[Graph] = getattr(proc, 'graph')
            graphs = () if graph is None else (graph, )
        else:
            raise AttributeError('Unable to find graphs in Processor')

        for graph in graphs:
            if graph.getName() == name:
                return graph
        raise KeyError(name)

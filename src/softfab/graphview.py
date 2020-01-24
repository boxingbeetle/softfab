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
from softfab.webgui import Widget
from softfab.xmlgen import XMLContent, txt, xhtml

try:
    from pygraphviz import AGraph
    canCreateGraphs = True
except ImportError:
    AGraph = object
    canCreateGraphs = False


svgNamespace = 'http://www.w3.org/2000/svg'
xlinkNamespace = 'http://www.w3.org/1999/xlink'

# Register namespaces with the ElementTree module.
# This is not strictly necessary, but without this ElementTree will generate
# synthetic names like "ns0", which makes the XML output harder to read.
ElementTree.register_namespace('svg', svgNamespace)
ElementTree.register_namespace('xlink', xlinkNamespace)

svgNSPrefix = '{%s}' % svgNamespace


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

    def __init__(self, name: str, graph: Optional[AGraph]):
        self.__name = name
        self.__graph = graph

    @property
    def name(self) -> str:
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
    """Holds the data for creating a graph."""

    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def populate(self, graph: AGraph, links: bool) -> None:
        raise NotImplementedError

    def build(self, export: bool, links: bool) -> Graph:
        """Creates a populated graph.

        Any errors are logged and not propagated.

        @param export: optimize the graph for use outside of the Control Center
                       (mailing, printing)?
        @param links: include hyperlinks?
        """

        name = self._name

        if not canCreateGraphs:
            return Graph(name, None)

        try:
            graph = AGraph(directed=True, strict=True, id=name)
            graph.node_attr.update(_defaultNodeAttrib)
            graph.edge_attr.update(_defaultEdgeAttrib)
            graph.graph_attr.update(_defaultGraphAttrib)
            graph.graph_attr.update(bgcolor=('white' if export
                                                else 'transparent'))
            self.populate(graph, links)
            return Graph(name, graph)
        except Exception:
            logging.exception(
                'Execution graph creation (pygraphviz) failed'
                )
            return Graph(name, None)


class ExecutionGraphBuilder(GraphBuilder):

    def __init__(self,
                 name: str,
                 products: Iterable[ProductDef] = (),
                 frameworks: Iterable[Framework] = ()
                 ):
        GraphBuilder.__init__(self, name)
        self._products = tuple(products)
        self._frameworks = tuple(frameworks)

    def populate(self, graph: AGraph, links: bool) -> None:
        for product in self._products:
            self.addProduct(graph, links, product)
        for framework in self._frameworks:
            self.addFramework(graph, links, framework)

    def addProduct(self,
                   graph: AGraph,
                   links: bool,
                   productDef: ProductDef
                   ) -> None:
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
        if links:
            nodeAttrib['URL'] = createProductDetailsURL(productId)

        productNodeId = 'prod.' + productId
        if not graph.has_node(productNodeId):
            graph.add_node(productNodeId, **nodeAttrib)

    def addFramework(self,
                     graph: AGraph,
                     links: bool,
                     framework: Framework
                     ) -> None:
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

        if links:
            nodeAttrib['URL'] = createFrameworkDetailsURL(frameworkId)

        frameworkNodeId = 'fw.' + frameworkId
        if not graph.has_node(frameworkNodeId):
            graph.add_node(frameworkNodeId, **nodeAttrib)

        for inputDefId in framework.getInputs():
            inputProductNodeId = 'prod.' + inputDefId
            if graph.has_node(inputProductNodeId):
                graph.add_edge(inputProductNodeId, frameworkNodeId)

        for outputDefId in framework.getOutputs():
            outputProductNodeId = 'prod.' + outputDefId
            if graph.has_node(outputProductNodeId):
                graph.add_edge(frameworkNodeId, outputProductNodeId)

def createExecutionGraphBuilder(name: str,
                                productIds: Iterable[str],
                                frameworkIds: Iterable[str]
                                ) -> ExecutionGraphBuilder:
    return ExecutionGraphBuilder(
        name,
        (productDefDB[productId] for productId in productIds),
        (frameworkDB[frameworkId] for frameworkId in frameworkIds)
        )

def createExecutionGraph(name: str,
                         productIds: Iterable[str],
                         frameworkIds: Iterable[str],
                         export: bool
                         ) -> Graph:
    builder = createExecutionGraphBuilder(name, productIds, frameworkIds)
    return builder.build(export, not export)

legendBuilder = ExecutionGraphBuilder(
    'legend',
    products=(
        ProductDef.create('product'),
        ProductDef.create('combined-product', combined=True),
        ProductDef.create('token-product', prodType=ProductType.TOKEN),
        ),
    frameworks=(
        Framework.create('framework', (), ()),
        ),
    )

def createLegend(export: bool) -> Graph:
    return legendBuilder.build(export, False)


class GraphPanel(Widget):
    '''Presents a graph on a panel, with the same frame and background as
    tables. The graph should be passed to the present method as "graph".
    '''

    def present(self, **kwargs: object) -> XMLContent:
        proc = cast(PageProcessor, kwargs.get('proc'))
        graph = cast(Graph, kwargs['graph'])
        return xhtml.div(class_ = 'graph')[
            xhtml.div[ graph.toSVG() ],
            None if proc is None else self.__presentFooter(proc, graph)
            ]

    def __presentFooter(self, proc: PageProcessor, graph: Graph) -> XMLContent:
        return xhtml.div(class_ = 'export')[
            'export: ', txt(', ').join(
                xhtml.a(
                    href = proc.subItemRelURL(f'{graph.name}.{fmt.ext}'),
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
            return super().getResponder(path, proc) # type: ignore[misc]
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
            if graph.name == name:
                return graph
        raise KeyError(name)

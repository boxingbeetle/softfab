# SPDX-License-Identifier: BSD-3-Clause

"""
Build execution graphs using Graphviz.
"""

from enum import Enum
from io import BytesIO
from typing import (
    AbstractSet, Generator, Iterable, Iterator, Optional, Set, Tuple, cast
)
from xml.etree import ElementTree
import logging
import re

from graphviz import Digraph
from twisted.internet import reactor
from twisted.internet.defer import Deferred, fail, inlineCallbacks
from twisted.internet.protocol import ProcessProtocol
from twisted.python.failure import Failure
import attr

from softfab.Page import PageProcessor, Responder
from softfab.frameworklib import Framework, frameworkDB
from softfab.pagelinks import (
    createFrameworkDetailsURL, createProductDetailsURL
)
from softfab.productdeflib import ProductDef, ProductType, productDefDB
from softfab.response import Response
from softfab.setcalc import UnionFind
from softfab.webgui import Widget
from softfab.xmlgen import XMLContent, xhtml

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
    DOT = ('dot', 'Graphviz dot file', 'application/x-graphviz; charset=UTF-8')

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

class RenderConsumer:
    """Consumes one rendering from a stream.
    The `deferred` will be called with the concrete render consumer as
    its argument, from which format-specific output can be retrieved.
    """

    def __init__(self) -> None:
        self.deferred = Deferred()

    def write(self, data: bytes) -> None:
        """Consumes data from the stream.
        Can be called multiple times, when new data becomes available.
        """
        raise NotImplementedError

    def fail(self, failure: Failure) -> None:
        """Called when the production failed.
        The producer will not make any further calls.
        """
        self.deferred.errback(failure)

    def done(self) -> None:
        """Called when the end of the stream was reached without errors.
        Note that it is possible that the data was truncated, but that
        can only be verified by the consumer, not by the producer.
        The producer will not make any further calls.
        """
        self.deferred.callback(self)

class BufferingRenderConsumer(RenderConsumer):

    def __init__(self) -> None:
        super().__init__()
        self.buffer = BytesIO()

    def write(self, data: bytes) -> None:
        self.buffer.write(data)

    def takeData(self) -> bytes:
        """Retrieve the buffered data.
        Can be called only once.
        """
        buffer = self.buffer
        data = buffer.getvalue()
        buffer.close()
        return data

class SVGRenderConsumer(RenderConsumer):

    def __init__(self) -> None:
        super().__init__()
        self.parser = ElementTree.XMLParser()

    def write(self, data: bytes) -> None:
        try:
            self.parser.feed(data)
        except ElementTree.ParseError:
            logging.exception('XML received from Graphviz is invalid')
            raise RuntimeError('See log for details')

    def takeSVG(self) -> ElementTree.Element:
        """Retrieve the SVG image.
        Can be called only once.
        """

        try:
            svgElement = self.parser.close()
        except ElementTree.ParseError:
            logging.exception('XML received from Graphviz is invalid')
            raise RuntimeError('See log for details')

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

@attr.s(auto_attribs=True)
class DotProcess(ProcessProtocol):
    """Handles the execution of the Graphviz 'dot' tool."""

    data: bytes
    consumer: RenderConsumer

    def connectionMade(self) -> None:
        self.transport.write(self.data)
        self.transport.closeStdin()

    def outReceived(self, data: bytes) -> None:
        self.consumer.write(data)

    def errReceived(self, data: bytes) -> None:
        logging.warning('Graphviz "dot" tool printed on stderr:\n%s',
                        data.decode(errors='replace'))

    def processEnded(self, reason: Failure) -> None:
        code = reason.value.exitCode
        if code == 0:
            self.consumer.done()
        else:
            logging.warning('Graphviz "dot" tool exited with code %d', code)
            self.consumer.fail(Failure(RuntimeError('See log for details')))

class Graph:
    '''Wrapper around Graphviz graphs.
    Use a GraphBuilder subclass to construct graphs.
    '''

    def __init__(self, graph: Digraph):
        self.__graph = graph

    def _runDot(self, fmt: GraphFormat, consumer: RenderConsumer) -> Deferred:
        data = self.__graph.source.encode()

        proc = DotProcess(data, consumer)
        executable = 'dot'
        args = ('dot', f'-T{fmt.ext}')
        try:
            reactor.spawnProcess(proc, executable, args)
        except OSError:
            logging.exception('Failed to spawn Graphviz "dot" tool')
            return fail(RuntimeError('See log for details'))

        return consumer.deferred

    @inlineCallbacks
    def export(self,
               fmt: GraphFormat
               ) -> Generator[Deferred, RenderConsumer, bytes]:
        '''Renders this graph in the given format.
        Returns a `Deferred` that on success delivers the rendered graph data,
        which is of type `bytes`.
        '''
        if fmt is GraphFormat.DOT:
            return self.__graph.source.encode()
        elif fmt is GraphFormat.SVG:
            consumer = yield self._runDot(GraphFormat.SVG, SVGRenderConsumer())
            assert isinstance(consumer, SVGRenderConsumer), consumer
            return ElementTree.tostring(consumer.takeSVG(), encoding='utf-8')
        else:
            consumer = yield self._runDot(fmt, BufferingRenderConsumer())
            assert isinstance(consumer, BufferingRenderConsumer), consumer
            return consumer.takeData()

    def toSVG(self) -> Deferred:
        '''Renders this graph as SVG image and cleans up the resulting SVG.
        The returned Deferred will deliver an SVGRenderConsumer on success.
        '''
        return self._runDot(GraphFormat.SVG, SVGRenderConsumer())

class GraphBuilder:
    """Holds the data for creating a graph."""

    def __init__(self, name: str, links: bool):
        self._name = name
        self._links = links

    @property
    def name(self) -> str:
        return self._name

    def populate(self, graph: Digraph, links: bool) -> None:
        raise NotImplementedError

    def build(self, export: bool) -> Graph:
        """Creates a populated graph.

        @param export: optimize the graph for use outside of the Control Center
                       (mailing, printing)?
        """

        graph = Digraph(graph_attr=dict(_defaultGraphAttrib, id=self._name),
                        node_attr=_defaultNodeAttrib,
                        edge_attr=_defaultEdgeAttrib,
                        strict=True)
        graph.attr(bgcolor=('white' if export else 'transparent'))
        self.populate(graph, self._links and not export)
        return Graph(graph)


class ExecutionGraphBuilder(GraphBuilder):

    def __init__(self,
                 name: str, *,
                 links: bool = True,
                 products: Iterable[ProductDef] = (),
                 frameworks: Iterable[Framework] = ()
                 ):
        GraphBuilder.__init__(self, name, links)
        self._products = tuple(products)
        self._frameworks = tuple(frameworks)

    def populate(self, graph: Digraph, links: bool) -> None:
        productIds = set()
        for product in self._products:
            self.addProduct(graph, links, product)
            productIds.add(product.getId())
        for framework in self._frameworks:
            self.addFramework(graph, links, framework, productIds)

    def addProduct(self,
                   graph: Digraph,
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
            nodeAttrib['URL'] = '../' + createProductDetailsURL(productId)
            nodeAttrib['target'] = '_parent'

        graph.node(f'prod.{productId}', **nodeAttrib)

    def addFramework(self,
                     graph: Digraph,
                     links: bool,
                     framework: Framework,
                     productIds: AbstractSet[str]
                     ) -> None:
        '''Add a node for the given framework to this graph.
        Also adds edges between the framework its inputs and outputs,
        for those products included in `productIds`.
        '''
        frameworkId = framework.getId()
        nodeAttrib = dict(
            label = frameworkId,
            shape = 'oval',
            )

        if links:
            nodeAttrib['URL'] = '../' + createFrameworkDetailsURL(frameworkId)
            nodeAttrib['target'] = '_parent'

        frameworkNodeId = f'fw.{frameworkId}'
        graph.node(frameworkNodeId, **nodeAttrib)

        for inputDefId in framework.getInputs():
            if inputDefId in productIds:
                graph.edge(f'prod.{inputDefId}', frameworkNodeId)

        for outputDefId in framework.getOutputs():
            if outputDefId in productIds:
                graph.edge(frameworkNodeId, f'prod.{outputDefId}')

def createExecutionGraphBuilder(name: str,
                                productIds: Iterable[str],
                                frameworkIds: Iterable[str]
                                ) -> ExecutionGraphBuilder:
    return ExecutionGraphBuilder(
        name,
        products=(productDefDB[productId] for productId in productIds),
        frameworks=(frameworkDB[frameworkId] for frameworkId in frameworkIds)
        )

legendBuilder = ExecutionGraphBuilder(
    'legend',
    links=False,
    products=(
        ProductDef.create('product'),
        ProductDef.create('combined-product', combined=True),
        ProductDef.create('token-product', prodType=ProductType.TOKEN),
        ),
    frameworks=(
        Framework.create('framework', (), ()),
        ),
    )


class GraphPanel(Widget):
    '''Presents a graph on a panel, with the same frame and background as
    tables.

    The graph builder should be passed to the present method as "graph".
    '''

    def present(self, **kwargs: object) -> XMLContent:
        proc = cast(PageProcessor, kwargs['proc'])
        name = cast(GraphBuilder, kwargs['graph']).name
        return xhtml.div(class_ = 'graph')[
            xhtml.div[
                xhtml.object(
                    data=proc.subItemRelURL(f'{name}.ui.svg'),
                    type='image/svg+xml'
                    )
                ],
            self.__presentFooter(proc, name)
            ]

    def __presentFooter(self, proc: PageProcessor, name: str) -> XMLContent:
        return xhtml.div(class_ = 'export')[
            'export: ', xhtml[', '].join(
                xhtml.a(
                    href = proc.subItemRelURL(f'{name}.{fmt.ext}'),
                    title = fmt.description,
                    )[ fmt.ext ]
                for fmt in GraphFormat
                )
            ]

class _GraphResponder(Responder):

    def __init__(self,
                 builder: GraphBuilder,
                 fileName: str,
                 fmt: GraphFormat,
                 export: bool
                 ):
        Responder.__init__(self)
        self.__builder = builder
        self.__fileName = fileName
        self.__format = fmt
        self.__export = export

    def respond(self, response: Response) -> Deferred:
        export = self.__export
        graph = self.__builder.build(export)
        fmt = self.__format
        response.setHeader('Content-Type', fmt.mediaType)
        if export:
            response.setFileName(f'{self.__fileName}.{fmt.ext}')
        else:
            response.allowEmbedding()
        return graph.export(fmt).addErrback(self.graphError, response)

    def graphError(self, reason: Failure, response: Response) -> str:
        response.setStatus(500, 'Graph rendering failed')
        response.setHeader('Content-Type', 'text/plain')
        return f'Graph rendering failed: {reason.value}'


class GraphPageMixin:
    __reGraphPath = re.compile(r'(\w+)(\.ui)?\.(\w+)')

    def getResponder(self,
                     path: Optional[str],
                     proc: PageProcessor
                     ) -> Responder:
        if path is None:
            return super().getResponder(path, proc) # type: ignore[misc]
        match = self.__reGraphPath.match(path)
        if match is None:
            raise KeyError("Subitem path is not of the form 'file.ext'")
        name, ui, formatStr = match.groups()
        try:
            builder = self.__getBuilder(proc, name)
        except KeyError as ex:
            raise KeyError(f'Unknown graph "{name}"') from ex
        try:
            fmt = GraphFormat[formatStr.upper()]
        except ValueError as ex:
            raise KeyError(f'Unknown file format "{formatStr}"') from ex
        return _GraphResponder(builder, name, fmt, not ui)

    def __getBuilder(self, proc: PageProcessor, name: str) -> GraphBuilder:
        if hasattr(proc, 'graphs'):
            builders: Iterable[GraphBuilder] = getattr(proc, 'graphs', ())
        elif hasattr(proc, 'graph'):
            builder: Optional[GraphBuilder] = getattr(proc, 'graph')
            if builder is None:
                builders = ()
            else:
                builders = (builder, )
        else:
            raise AttributeError('Unable to find graphs in Processor')

        for builder in builders:
            if builder.name == name:
                return builder
        raise KeyError(name)

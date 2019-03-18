# SPDX-License-Identifier: BSD-3-Clause

'''
Builds the execution graphs by using AGraph from the pygraphviz module.
'''

from typing import Optional
from xml.etree import ElementTree
import logging
import re

from softfab.Page import PageProcessor, Responder
from softfab.frameworklib import Framework, frameworkDB
from softfab.graphrefs import Format, iterGraphFormats
from softfab.pagelinks import (
    createFrameworkDetailsURL, createProductDetailsURL
)
from softfab.productdeflib import ProductDef, ProductType, productDefDB
from softfab.setcalc import UnionFind
from softfab.svglib import SVGPanel, svgNSPrefix
from softfab.xmlgen import txt, xhtml

try:
    from pygraphviz import AGraph
except ImportError:
    canCreateGraphs = False
else:
    canCreateGraphs = True

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

def iterConnectedExecutionGraphs():
    '''Returns a collection of (weakly) connected execution graphs.
    For each execution graph, the collection contains a pair with the products
    and frameworks in that connected graph.
    '''
    unionFind = UnionFind()

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

    def __init__(self, name, graph):
        self.__name = name
        self.__graph = graph

    def getName(self):
        return self.__name

    def export(self, fmt):
        '''Renders this graph in the given format.
        Returns the rendered graph data, or None if rendering failed.
        '''
        graph = self.__graph
        if graph is None:
            return None
        try:
            if fmt is Format.dot:
                return graph.string()
            elif fmt is Format.svg:
                svgElement = self.toSVG()
                if svgElement is None:
                    return None
                return ElementTree.tostring(svgElement, 'utf-8')
            else:
                return graph.draw(format = str(fmt), prog = 'dot')
        except Exception:
            logging.exception(
                'Execution graph export failed'
                )
            return None

    def toSVG(self):
        '''Renders this graph as SVG image and cleans up the resulting SVG.
        Returns an ElementTree instance, or None if graph rendering failed
        (e.g. pygraphviz not installed; bug in pygraphviz; invalid arguments
        passed by our code, etc.).
        '''
        graph = self.__graph
        if graph is None:
            return None

        try:
            # Note: This catches exceptions from the rendering process
            svgGraph = graph.draw(format = 'svg', prog = 'dot')
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

    def __init__(self, export, links):
        '''Creates a graph.
        Iff "export" is True, the graph is optimized for use outside of the
        Control Center (mailing, printing).
        '''
        self._export = export
        self._links = links
        self._graph = None

    def __createGraph(self, name, **kwargs):
        '''Creates an empty graph, passes it to the given populate() function
        and returns the result, or returns None if graph generation fails.
        Any errors are logged and not propagated.
        '''
        if not canCreateGraphs:
            return
        try:
            graph = AGraph(directed = True, strict = True, id = name)
            graph.node_attr.update(_defaultNodeAttrib)
            graph.edge_attr.update(_defaultEdgeAttrib)
            graph.graph_attr.update(_defaultGraphAttrib)

            if self._export:
                graph.graph_attr.update(bgcolor = 'white')
            else:
                graph.graph_attr.update(bgcolor = 'transparent')

            self._graph = graph
            self.populate(**kwargs)
        except Exception:
            logging.exception(
                'Execution graph creation (pygraphviz) failed'
                )

    def populate(self, **kwargs):
        raise NotImplementedError

    @classmethod
    def build(cls, name, export, links, **kwargs):
        builder = cls(export, links)
        GraphBuilder.__createGraph(builder, name, **kwargs)
        # pylint: disable=protected-access
        #print '***Graph %s *** ' % name # for debugging purposes
        #print builder._graph.string() # for debugging purposes

        return Graph(name, builder._graph)

class ExecutionGraphBuilder(GraphBuilder):

    def populate(self, **kwargs):
        raise NotImplementedError

    def addProduct(self, productDef):
        '''Add a node for the given product to this graph.
           Specify node attribs if product is a token and/or combined product
        '''
        productId = productDef.getId()
        nodeAttrib = dict(
            label = str(productId),
            shape = 'box',
            peripheries = '2' if productDef.isCombined() else '1',
            )
        if productDef['type'] is ProductType.TOKEN:
            nodeAttrib['style'] = _defaultNodeAttrib['style'] + ',dashed'
        if self._links:
            nodeAttrib['URL'] = createProductDetailsURL(productId)

        productNodeId = str('prod.' + productId)
        if not self._graph.has_node(productNodeId):
            self._graph.add_node(productNodeId, **nodeAttrib)

    def addFramework(self, framework):
        '''Add a node for the given framework to this graph.
        Also adds edges between the framework to all previously added products
        that are an input or output of this framework.
        Pre-condition: make sure products are added first!
        '''
        frameworkId = framework.getId()
        nodeAttrib = dict(
            label = str(frameworkId),
            shape = 'oval',
            )

        if self._links:
            nodeAttrib['URL'] = createFrameworkDetailsURL(frameworkId)

        frameworkNodeId = str('fw.' + frameworkId)
        if not self._graph.has_node(frameworkNodeId):
            self._graph.add_node(frameworkNodeId, **nodeAttrib)

        for inputDefId in framework.getInputs():
            inputProductNodeId = str('prod.' + inputDefId)
            if self._graph.has_node(inputProductNodeId):
                self._graph.add_edge(inputProductNodeId, frameworkNodeId)

        for outputDefId in framework.getOutputs():
            outputProductNodeId = str('prod.' + outputDefId)
            if self._graph.has_node(outputProductNodeId):
                self._graph.add_edge(frameworkNodeId, outputProductNodeId)

class _DBExecutionGraphBuilder(ExecutionGraphBuilder):

    def populate(self, productIds, frameworkIds): # pylint: disable=arguments-differ
        for productId in productIds:
            self.addProduct(productDefDB[productId])
        for frameworkId in frameworkIds:
            self.addFramework(frameworkDB[frameworkId])

def createExecutionGraph(name, productIds, frameworkIds, export):
    return _DBExecutionGraphBuilder.build(
        name, export, not export,
        productIds = productIds, frameworkIds = frameworkIds
        )

class _LegendBuilder(ExecutionGraphBuilder):

    def populate(self): # pylint: disable=arguments-differ
        self.addFramework(Framework.create('framework', (), ()))
        self.addProduct(ProductDef.create('product'))
        self.addProduct(ProductDef.create('combined-product', combined = True))
        self.addProduct(
            ProductDef.create('token-product', prodType = ProductType.TOKEN)
            )

def createLegend(export):
    return _LegendBuilder.build('legend', export, False)


class GraphPanel(SVGPanel):
    '''Presents a graph on a panel, with the same frame and background as
    tables. The graph should be passed to the present method as "graph".
    '''

    def present(self, *, graph, **kwargs): # pylint: disable=arguments-differ
        svgElement = graph.toSVG()
        if svgElement is None:
            return None
        else:
            return super().present(graph=graph, svgElement=svgElement, **kwargs)

    def presentFooter(self, proc, graph, **kwargs): # pylint: disable=arguments-differ
        return xhtml.div(class_ = 'export')[
            'export: ', txt(', ').join(
                xhtml.a(
                    href = proc.subItemRelURL(
                        '%s.%s' % (graph.getName(), fmt.ext)
                        ),
                    title = fmt.description,
                    )[ fmt.ext ]
                for fmt in iterGraphFormats()
                )
            ]

class _GraphResponder(Responder):

    def __init__(self, graph, fileName, fmt):
        Responder.__init__(self)
        self.__graph = graph
        self.__fileName = fileName
        self.__format = fmt

    def respond(self, response):
        fmt = self.__format
        response.setHeader('Content-Type', fmt.mediaType)
        response.setFileName('%s.%s' % ( self.__fileName, fmt.ext ))
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
            graph = self.getGraph(proc, name)
        except KeyError:
            raise KeyError('Unknown graph "%s"' % name)
        try:
            # https://github.com/PyCQA/pylint/issues/2159
            fmt = Format(formatStr) # pylint: disable=no-value-for-parameter
        except ValueError:
            raise KeyError('Unknown file format "%s"' % formatStr)
        return _GraphResponder(graph, name, fmt)

    def getGraph(self, proc, name):
        if hasattr(proc, 'graphs'):
            if proc.graphs is None:
                return None
            graphs = proc.graphs
        elif hasattr(proc, 'graph'):
            if proc.graph is None:
                return None
            graphs = (proc.graph, )
        else:
            raise AttributeError('Unable to find graphs in Processor')

        for graph in graphs:
            if graph.getName() == name:
                return graph
        raise KeyError(name)

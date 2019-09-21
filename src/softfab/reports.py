# SPDX-License-Identifier: BSD-3-Clause

from codecs import getreader
from typing import (
    IO, Any, Callable, Iterable, Iterator, Optional, Sequence, Tuple
)
from xml.etree.ElementTree import ElementTree, ParseError, parse

from pygments.lexer import Lexer
from pygments.lexers import guess_lexer_for_filename
from pygments.token import STANDARD_TYPES
from pygments.util import ClassNotFound
from twisted.web.http import Request as TwistedRequest
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
import attr

from softfab.StyleResources import pygmentsFormatter, pygmentsSheet, styleRoot
from softfab.UIPage import factoryStyleSheet, fixedHeadItems
from softfab.webgui import Column, Table
from softfab.xmlbind import bindElement
from softfab.xmlgen import XMLContent, XMLNode, XMLSubscriptable, xhtml

TokenType = object

def presentTokens(tokens: Iterator[Tuple[TokenType, str]]) -> XMLContent:
    for ttype, value in tokens:
        cssclass = STANDARD_TYPES.get(ttype, '')
        if cssclass:
            span: XMLSubscriptable = xhtml.span(class_=cssclass)
        else:
            span = xhtml

        parts = value.split('\n')
        for part in parts[:-1]:
            yield span[part]
            yield '\n'
        yield span[parts[-1]]

def presentBlock(tokens: Iterator[Tuple[TokenType, str]]) -> XMLNode:
    return xhtml.pre(class_=pygmentsFormatter.cssclass)[
        presentTokens(tokens)
        ]

@attr.s(auto_attribs=True)
class PygmentedResource(Resource):
    """Presents a text artifact using Pygments syntax highlighting.
    """
    isLeaf = True

    message: XMLContent
    text: str
    fileName: str
    lexer: Lexer

    def render_GET(self, request: TwistedRequest) -> object:
        depth = len(request.prepath) - 1
        styleURL = '../' * depth + styleRoot.relativeURL
        request.write(b'<!DOCTYPE html>\n')
        request.write(
            xhtml.html[
                xhtml.head[
                    fixedHeadItems,
                    pygmentsSheet,
                    xhtml.title[f'Report: {self.fileName}']
                    ].present(styleURL=styleURL),
                xhtml.body[
                    self.message,
                    presentBlock(self.lexer.get_tokens(self.text))
                    ]
                ].flattenXML().encode()
            )
        request.finish()
        return NOT_DONE_YET

@attr.s(auto_attribs=True)
class JUnitSuite:
    name: str = 'nameless'
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    time: float = 0

def findJUnitSuites(tree: ElementTree) -> Sequence[JUnitSuite]:
    """Looks for JUnit-style test suite results in the given XML."""

    root = tree.getroot()
    if root.tag == 'testsuites':
        suites = [child for child in root if child.tag == 'testsuite']
    elif root.tag == 'testsuite':
        # pytest outputs a single suite as the root element.
        suites = [root]
    else:
        suites = []

    return [bindElement(suite, JUnitSuite) for suite in suites]

@attr.s(auto_attribs=True)
class JUnitResource(Resource):
    """Presents a text artifact using Pygments syntax highlighting.
    """
    isLeaf = True

    suites: Sequence[JUnitSuite]
    fileName: str

    def render_GET(self, request: TwistedRequest) -> object:
        depth = len(request.prepath) - 1
        styleURL = '../' * depth + styleRoot.relativeURL
        request.write(b'<!DOCTYPE html>\n')
        request.write(
            xhtml.html[
                xhtml.head[
                    fixedHeadItems,
                    factoryStyleSheet,
                    xhtml.title[f'Report: {self.fileName}']
                    ].present(styleURL=styleURL),
                xhtml.body[
                    xhtml.div(class_='body')[
                        JUnitSummary.instance.present(suites=self.suites),
                        self.presentSuites()
                        ]
                    ]
                ].flattenXML().encode()
            )
        request.finish()
        return NOT_DONE_YET

    def presentSuites(self) -> XMLContent:
        for suite in self.suites:
            yield xhtml.h2[suite.name]

class JUnitSummary(Table):

    columns = (
        'Suite',
        Column(cellStyle='rightalign', label='Duration'),
        Column(cellStyle='rightalign', label='Tests'),
        Column(cellStyle='rightalign', label='Failures'),
        Column(cellStyle='rightalign', label='Errors'),
        Column(cellStyle='rightalign', label='Skipped'),
        )

    def iterRows(self, **kwargs: Any) -> Iterator[XMLContent]:
        suites: Iterable[JUnitSuite] = kwargs['suites']
        for suite in suites:
            yield (
                suite.name, f'{suite.time:1.3f}', suite.tests,
                suite.failures, suite.errors, suite.skipped
                )

UTF8Reader = getreader('utf-8')

def createPresenter(opener: Callable[[], IO[bytes]],
                    fileName: str
                    ) -> Optional[Resource]:
    """Attempt to create a custom presenter for the given artifact.
    Return a resource that handles the presentation, or None if no custom
    presentation is available or desired for this artifact.
    """

    # TODO: Perform file type detection to see if we want to do custom
    #       presentation.
    #       We can probably combine mimetypes.guess_type with the info
    #       from Pygments into a new detection function that's also used
    #       by the 'artifacts' module.
    #       Do not use source highlighting for formats that the browser
    #       can handle in non-source form, like HTML and SVG.
    message = None
    if fileName.endswith('.xml'):
        try:
            with opener() as stream:
                tree = parse(stream)
            try:
                suites = findJUnitSuites(tree)
            except Exception as ex:
                message = xhtml.p[xhtml.b['Bad JUnit data:'], f' {ex}']
            else:
                if suites:
                    return JUnitResource(suites, fileName)
        except ParseError as ex:
            message = xhtml.p[xhtml.b['Invalid XML:'], f' {ex}']
    else:
        return None

    # Load file contents into a string.
    # TODO: Use encoding information from the XML parsing, if available.
    # TODO: Do we want to display the original text or pretty-print the
    #       parsed version?
    with opener() as stream:
        with UTF8Reader(stream, errors='replace') as reader:
            text = reader.read()

    try:
        lexer = guess_lexer_for_filename(fileName, text)
    except ClassNotFound:
        return None
    else:
        return PygmentedResource(message, text, fileName, lexer)

# SPDX-License-Identifier: BSD-3-Clause

from codecs import getreader
from collections import defaultdict
from mimetypes import guess_type
from typing import (
    IO, Any, Callable, DefaultDict, Iterable, Iterator, List, Optional, Tuple
)

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
from softfab.reportlib import JUnitCase, JUnitReport, JUnitSuite, parseReport
from softfab.resultcode import ResultCode
from softfab.webgui import Column, Table, cell
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

    message: Optional[str]
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
                    self.presentMessage(),
                    presentBlock(self.lexer.get_tokens(self.text))
                    ]
                ].flattenXML().encode()
            )
        request.finish()
        return NOT_DONE_YET

    def presentMessage(self) -> XMLContent:
        message = self.message
        if not message:
            return None

        details: Optional[str]
        index = message.find(':') + 1
        if index:
            details = message[index:]
            message = message[:index]
        else:
            details = None

        return xhtml.p[xhtml.b[message], details]

resultMap = {
    ResultCode.OK: 'pass',
    ResultCode.WARNING: 'fail',
    }

@attr.s(auto_attribs=True)
class JUnitResource(Resource):
    """Presents a text artifact using Pygments syntax highlighting.
    """
    isLeaf = True

    report: JUnitReport
    fileName: str

    def render_GET(self, request: TwistedRequest) -> object:
        depth = len(request.prepath) - 1
        styleURL = '../' * depth + styleRoot.relativeURL
        suites = self.report.testsuite
        showChecks = any(suite.tests != len(suite.testcase) for suite in suites)

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
                        JUnitSummary.instance.present(
                            suites=suites, showChecks=showChecks
                            ),
                        self.presentSuites()
                        ]
                    ]
                ].flattenXML().encode()
            )
        request.finish()
        return NOT_DONE_YET

    def presentSuites(self) -> XMLContent:
        for suite in self.report.testsuite:
            yield xhtml.h2[suite.name]
            yield JUnitSuiteTable.instance.present(suite=suite)

            anyFailures = False
            yield xhtml.h3['Failures']
            for case in suite.testcase:
                if case.result is ResultCode.WARNING:
                    anyFailures = True
                    yield self.presentFailure(case)
            if not anyFailures:
                yield xhtml.p['None.']

    headerSep = xhtml[' \u25B8 ']

    def presentFailure(self, case: JUnitCase) -> XMLContent:
        for number, failure in enumerate(case.failure, start=1):
            header = [case.classname, case.name]
            if len(case.failure) > 1:
                header.append(f'{number} of {len(case.failure)}')
            yield xhtml.h4[self.headerSep.join(header)]

            message = failure.message
            if message:
                yield xhtml.p[message]

            text = failure.text
            if text:
                yield xhtml.pre[xhtml.code[text]]

class JUnitSummary(Table):
    style = 'nostrong'

    suiteColumn = Column(label='Suite')
    durationColumn = Column(cellStyle='rightalign', label='Duration')
    testsColumn = Column(cellStyle='rightalign', label='Tests')
    checksColumn = Column(cellStyle='rightalign', label='Checks')
    failuresColumn = Column(cellStyle='rightalign', label='Failures')
    errorsColumn = Column(cellStyle='rightalign', label='Errors')
    skippedColumn = Column(cellStyle='rightalign', label='Skipped')

    def iterColumns(self, **kwargs: Any) -> Iterator[Column]:
        showChecks: bool = kwargs['showChecks']
        yield self.suiteColumn
        yield self.durationColumn
        yield self.testsColumn
        if showChecks:
            yield self.checksColumn
        yield self.failuresColumn
        yield self.errorsColumn
        yield self.skippedColumn

    def iterRows(self, **kwargs: Any) -> Iterator[XMLContent]:
        showChecks: bool = kwargs['showChecks']
        suites: Iterable[JUnitSuite] = kwargs['suites']
        for suite in suites:
            row: List[XMLContent] = [suite.name, f'{suite.time:1.3f}']
            if showChecks:
                row.append(len(suite.testcase))
            row.append(suite.tests)
            for count, result in zip(
                    (suite.failures, suite.errors, suite.skipped),
                    (ResultCode.WARNING, ResultCode.ERROR, ResultCode.CANCELLED)
                    ):
                style=None if count == 0 else result
                row.append(cell(class_=style)[count])
            yield row

class JUnitSuiteTable(Table):
    style = 'nostrong'

    columns = (
        'Class Name',
        'Test Case',
        Column(cellStyle='rightalign', label='Duration'),
        'Result',
        )

    def iterRows(self, **kwargs: Any) -> Iterator[XMLContent]:
        suite: JUnitSuite = kwargs['suite']
        casesByClass: DefaultDict[str, List[JUnitCase]] = defaultdict(list)
        for case in suite.testcase:
            casesByClass[case.classname].append(case)
        for classname, cases in casesByClass.items():
            for idx, case in enumerate(cases):
                result = case.result
                row: List[XMLContent] = []
                if idx == 0:
                    row.append(cell(rowspan=len(cases))[classname])
                row.append(case.name)
                row.append(f'{case.time:1.3f}')
                row.append(cell(class_=result)[resultMap[result]])
                yield row

UTF8Reader = getreader('utf-8')

def createPresenter(opener: Callable[[], IO[bytes]],
                    fileName: str
                    ) -> Optional[Resource]:
    """Attempt to create a custom presenter for the given artifact.
    Return a resource that handles the presentation, or None if no custom
    presentation is available or desired for this artifact.
    """

    message: Optional[str]
    try:
        report = parseReport(opener, fileName)
    except ValueError as ex:
        message = str(ex)
    else:
        if isinstance(report, JUnitReport):
            return JUnitResource(report, fileName)
        message = None

    # TODO: Perform file type detection to see if we want to do custom
    #       presentation.
    #       We can probably combine mimetypes.guess_type with the info
    #       from Pygments into a new detection function that's also used
    #       by the 'artifacts' module.

    # Only use source highlighting for text formats, except for HTML.
    if message is None:
        contentType, contentEncoding = guess_type(fileName, strict=False)
        if not contentType or not contentType.startswith('text/'):
            return None
        if contentType == 'text/html':
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

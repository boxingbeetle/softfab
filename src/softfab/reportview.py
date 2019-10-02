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
import attr

from softfab.StyleResources import pygmentsFormatter, pygmentsSheet
from softfab.UIPage import factoryStyleSheet
from softfab.reportlib import JUnitCase, JUnitReport, JUnitSuite, parseReport
from softfab.resultcode import ResultCode
from softfab.webgui import Column, Table, cell
from softfab.xmlgen import XMLContent, xhtml


class ReportPresenter:
    """Abstract base class for code that presents reports as HTML."""

    def headItems(self) -> XMLContent:
        """The header items specific to this type of report.
        The default implementation returns nothing.
        """
        return None

    def presentBody(self) -> XMLContent:
        """Present the body of the report."""
        raise NotImplementedError

TokenType = object

def _splitLines(
        tokens: Iterator[Tuple[TokenType, str]]
        ) -> Iterator[XMLContent]:
    for ttype, value in tokens:
        cssclass = STANDARD_TYPES.get(ttype)
        span = xhtml.span(class_=cssclass) if cssclass else None

        first = True
        for part in value.split('\n'):
            if first:
                first = False
            else:
                yield '\n'
            if part:
                yield part if span is None else span[part]

class PygmentedTable(Table):
    style = pygmentsFormatter.cssclass

    columns = (Column(cellStyle='lineno'), Column())

    def iterRows(self, **kwargs: Any) -> Iterator[XMLContent]:
        tokens: Iterator[Tuple[TokenType, str]] = kwargs['tokens']

        lineNo = 1
        nodes: List[XMLContent] = []
        for node in _splitLines(tokens):
            if node == '\n':
                yield (
                    xhtml.a(id=f'L{lineNo}'),
                    xhtml.a(href=f'#L{lineNo}')[lineNo]
                    ), nodes
                lineNo += 1
                nodes = []
            else:
                nodes.append(node)
        if nodes:
            yield lineNo, nodes

@attr.s(auto_attribs=True)
class PygmentedPresenter(ReportPresenter):
    """Presents a text artifact using Pygments syntax highlighting."""

    message: Optional[str]
    text: str
    lexer: Lexer

    def headItems(self) -> XMLContent:
        return pygmentsSheet

    def presentBody(self) -> XMLContent:
        yield self.presentMessage()
        yield PygmentedTable.instance.present(
            tokens=self.lexer.get_tokens(self.text)
            )

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
class JUnitPresenter(ReportPresenter):
    """Presents a JUnitReport as HTML."""

    report: JUnitReport

    def headItems(self) -> XMLContent:
        return factoryStyleSheet

    def presentBody(self) -> XMLContent:
        suites = self.report.testsuite
        yield JUnitSummary.instance.present(
            suites=suites,
            showChecks=any(suite.tests != len(suite.testcase)
                           for suite in suites)
            )
        for suite in suites:
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
                    ) -> Optional[ReportPresenter]:
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
            return JUnitPresenter(report)
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
        return PygmentedPresenter(message, text, lexer)

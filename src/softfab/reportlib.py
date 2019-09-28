# SPDX-License-Identifier: BSD-3-Clause

from typing import IO, Callable, List, Optional
from xml.etree.ElementTree import ElementTree, ParseError, parse

import attr

from softfab.resultcode import ResultCode
from softfab.xmlbind import bindElement


@attr.s(auto_attribs=True)
class JUnitFailure:
    message: str = ''
    text: str = ''

@attr.s(auto_attribs=True)
class JUnitCase:
    name: str = 'unknown'
    classname: str = ''
    file: str = ''
    line: int = 0
    time: float = 0
    failure: List[JUnitFailure] = attr.ib(factory=list)

    @property
    def result(self) -> ResultCode:
        if self.failure:
            return ResultCode.WARNING
        else:
            return ResultCode.OK

@attr.s(auto_attribs=True)
class JUnitSuite:
    name: str = 'nameless'
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    time: float = 0
    testcase: List[JUnitCase] = attr.ib(factory=list)

@attr.s(auto_attribs=True)
class JUnitReport:
    testsuite: List[JUnitSuite] = attr.ib(factory=list)

def parseXMLReport(tree: ElementTree) -> Optional[JUnitReport]:
    """Looks for supported report formats in the given XML."""

    root = tree.getroot()

    # JUnit-style reports.
    try:
        if root.tag == 'testsuites':
            return bindElement(root, JUnitReport)
        if root.tag == 'testsuite':
            # pytest outputs a single suite as the root element.
            return JUnitReport(testsuite=[bindElement(root, JUnitSuite)])
    except Exception as ex:
        raise ValueError(f'Bad JUnit data: {ex}') from ex

    return None

def parseReport(opener: Callable[[], IO[bytes]],
                fileName: str
                ) -> Optional[JUnitReport]:
    """Attempt to parse a task report.
    Return the report on success or None if no supported report format was
    detected.
    Raise ValueError when the report was in a recognized format but failed
    to parse.
    Raise OSError when there is a low-level error reading the report data.
    """
    if fileName.endswith('.xml'):
        try:
            with opener() as stream:
                tree = parse(stream)
        except ParseError as ex:
            raise ValueError(f'Invalid XML: {ex}') from ex
        else:
            return parseXMLReport(tree)
    else:
        return None

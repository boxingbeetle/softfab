# SPDX-License-Identifier: BSD-3-Clause

from itertools import chain
from typing import IO, Callable, Iterable, List, Mapping, Optional
from xml.etree.ElementTree import ElementTree, ParseError, parse

import attr

from softfab.resultcode import ResultCode
from softfab.xmlbind import bindElement


class Report:
    """Abstract base class for task reports."""

    @property
    def result(self) -> Optional[ResultCode]:
        """The result code of the task execution, or None if we are unable
        to determine the result.
        Note that a final verdict can be based on the results from multiple
        reports, so if a report only represents a part of the total task
        execution, it should just return the result of that part.
        """
        raise NotImplementedError

    @property
    def summary(self) -> str:
        """A short human-readable string describing the task result.
        If `result` returns None, the summary will be ignored.
        """
        raise NotImplementedError

    @property
    def data(self) -> Mapping[str, str]:
        """The mid-level data extracted from this report."""
        raise NotImplementedError

def _combineResults(results: Iterable[ResultCode]) -> ResultCode:
    """Combine multiple results into one.
    Skipped (CANCELLED) entries will be ignored.
    """
    CANCELLED = ResultCode.CANCELLED
    return max((result for result in results if result is not CANCELLED),
               default=CANCELLED)

@attr.s(auto_attribs=True)
class JUnitDetail:
    message: str = ''
    text: str = ''

@attr.s(auto_attribs=True)
class JUnitCase:
    name: str = 'unknown'
    classname: str = ''
    file: str = ''
    line: int = 0
    time: float = 0
    error: List[JUnitDetail] = attr.ib(factory=list)
    failure: List[JUnitDetail] = attr.ib(factory=list)
    skipped: List[JUnitDetail] = attr.ib(factory=list)

    @property
    def result(self) -> ResultCode:
        if self.error:
            return ResultCode.ERROR
        elif self.failure:
            return ResultCode.WARNING
        elif self.skipped:
            return ResultCode.CANCELLED
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

    @property
    def result(self) -> ResultCode:
        return _combineResults(chain(
            self.__statsResults(),
            (case.result for case in self.testcase)
            ))

    def __statsResults(self) -> Iterable[ResultCode]:
        """Results based on reported stats."""
        if self.errors:
            yield ResultCode.ERROR
        if self.failures:
            yield ResultCode.WARNING

@attr.s(auto_attribs=True)
class JUnitReport(Report):
    testsuite: List[JUnitSuite] = attr.ib(factory=list)

    @property
    def result(self) -> ResultCode:
        return _combineResults(suite.result for suite in self.testsuite)

    @property
    def summary(self) -> str:
        if self.numTestcases == 0:
            return 'no test cases found'
        elems = []
        errors = self.errors
        if errors:
            elems.append(f"{errors} error{'' if errors == 1 else 's'}")
        elems.append(f'{self.failures} failed')
        skipped = self.skipped
        if skipped:
            elems.append(f'{skipped} skipped')
        return ', '.join(elems)

    @property
    def data(self) -> Mapping[str, str]:
        return dict(
            testcases=str(self.numTestcases),
            checks=str(sum(suite.tests for suite in self.testsuite)),
            failures=str(self.failures),
            errors=str(self.errors),
            skipped=str(self.skipped),
            )

    @property
    def numTestcases(self) -> int:
        return sum(len(suite.testcase) for suite in self.testsuite)

    @property
    def failures(self) -> int:
        return sum(suite.failures for suite in self.testsuite)

    @property
    def errors(self) -> int:
        return sum(suite.errors for suite in self.testsuite)

    @property
    def skipped(self) -> int:
        return sum(suite.skipped for suite in self.testsuite)

def parseXMLReport(tree: ElementTree) -> Optional[Report]:
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
                ) -> Optional[Report]:
    """Attempt to parse a task report.
    Return the report on success or None if no supported report format was
    detected.
    Raise ValueError when the report was in a recognized format but failed
    to parse.
    Raise OSError when there is a low-level error reading the report data.
    """
    fileName = fileName.lower()
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

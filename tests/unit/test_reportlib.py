# SPDX-License-Identifier: BSD-3-Clause

from io import StringIO

from softfab.reportlib import parseReport
from softfab.resultcode import ResultCode


def testParsePytestEmpty():
    """Parse a report from pytest that contains no test cases."""

    xml = '''
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite errors="0" failures="0" hostname="hyperion" name="pytest" skipped="0" tests="0" time="0.569" timestamp="2020-08-14T01:10:52.311169"/>
</testsuites>
'''.lstrip()

    report = parseReport(lambda: StringIO(xml), 'report.xml')
    assert report is not None

    assert report.errors == 0
    assert report.failures == 0
    assert report.skipped == 0
    assert report.numTestcases == 0
    assert report.result is ResultCode.CANCELLED
    assert report.summary == 'no test cases found'
    data = report.data
    assert data['testcases'] == '0'
    assert data['checks'] == '0'
    assert data['failures'] == '0'
    assert data['errors'] == '0'
    assert data['skipped'] == '0'

    assert len(report.testsuite) == 1
    suite, = report.testsuite
    assert suite.tests == 0
    assert suite.failures == 0
    assert suite.errors == 0
    assert suite.skipped == 0
    assert suite.time == 0.569
    assert suite.result is ResultCode.CANCELLED

    assert not suite.testcase

def testParsePytestAllPass():
    """Parse a report from pytest where all tests pass."""

    xml = '''
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite errors="0" failures="0" hostname="hyperion" name="pytest" skipped="0" tests="3" time="1.234" timestamp="2020-08-13T13:03:59.945171">
    <testcase classname="test_databaselib" file="test_databaselib.py" line="117" name="testEmpty[Database]" time="0.216"/>
    <testcase classname="test_databaselib" file="test_databaselib.py" line="117" name="testEmpty[VersionedDatabase]" time="0.001"/>
    <testcase classname="test_databaselib" file="test_databaselib.py" line="338" name="testMixedRandom" time="0.749">
      <system-out>Random seed: 1597316644
</system-out>
    </testcase>
  </testsuite>
</testsuites>
'''.lstrip()

    report = parseReport(lambda: StringIO(xml), 'report.xml')
    assert report is not None

    assert report.errors == 0
    assert report.failures == 0
    assert report.skipped == 0
    assert report.numTestcases == 3
    assert report.result is ResultCode.OK
    assert report.summary == '0 failed'
    data = report.data
    assert data['testcases'] == '3'
    assert data['checks'] == '3'
    assert data['failures'] == '0'
    assert data['errors'] == '0'
    assert data['skipped'] == '0'

    assert len(report.testsuite) == 1
    suite, = report.testsuite
    assert suite.tests == 3
    assert suite.failures == 0
    assert suite.errors == 0
    assert suite.skipped == 0
    assert suite.time == 1.234
    assert suite.result is ResultCode.OK

    assert len(suite.testcase) == 3
    for case in suite.testcase:
        assert case.result is ResultCode.OK
        assert not case.error
        assert not case.failure
        assert not case.skipped


def testParsePytestSomeFail():
    """Parse a report from pytest where some tests fail."""

    xml = '''
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite errors="0" failures="1" hostname="hyperion" name="pytest" skipped="0" tests="3" time="1.234" timestamp="2020-08-13T13:03:59.945171">
    <testcase classname="test_databaselib" file="test_databaselib.py" line="117" name="testEmpty[Database]" time="0.216"/>
    <testcase classname="test_databaselib" file="test_databaselib.py" line="117" name="testEmpty[VersionedDatabase]" time="0.001"/>
    <testcase classname="test_joblib.TestJobs" file="test_joblib.py" line="444" name="test0110TRSetRandomRun" time="0.000">
      <failure message="RuntimeError: forced">self = &lt;test_joblib.TestJobs testMethod=test0110TRSetRandomRun&gt;

    def setUp(self):
&gt;       raise RuntimeError('forced')
E       RuntimeError: forced

test_joblib.py:45: RuntimeError</failure>
    </testcase>
  </testsuite>
</testsuites>
'''.lstrip()

    report = parseReport(lambda: StringIO(xml), 'report.xml')
    assert report is not None

    assert report.errors == 0
    assert report.failures == 1
    assert report.skipped == 0
    assert report.numTestcases == 3
    assert report.result is ResultCode.WARNING
    assert report.summary == '1 failed'
    data = report.data
    assert data['testcases'] == '3'
    assert data['checks'] == '3'
    assert data['failures'] == '1'
    assert data['errors'] == '0'
    assert data['skipped'] == '0'

    assert len(report.testsuite) == 1
    suite, = report.testsuite
    assert suite.tests == 3
    assert suite.failures == 1
    assert suite.errors == 0
    assert suite.skipped == 0
    assert suite.time == 1.234
    assert suite.result is ResultCode.WARNING

    assert len(suite.testcase) == 3
    for index, case in enumerate(suite.testcase):
        if index == 2:
            assert case.result is ResultCode.WARNING
            assert case.failure
        else:
            assert case.result is ResultCode.OK
            assert not case.failure
        assert not case.error
        assert not case.skipped


def testParsePytestSomeSkipped():
    """Parse a report from pytest where some tests were skipped."""

    xml = '''
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite errors="0" failures="0" hostname="hyperion" name="pytest" skipped="1" tests="3" time="1.234" timestamp="2020-08-13T13:03:59.945171">
    <testcase classname="test_databaselib" file="test_databaselib.py" line="117" name="testEmpty[Database]" time="0.216"/>
    <testcase classname="test_databaselib" file="test_databaselib.py" line="117" name="testEmpty[VersionedDatabase]" time="0.001"/>
    <testcase classname="test_taskrunnerlib" file="test_taskrunnerlib.py" line="211" name="testTaskRunnerToXML[data0]" time="0.000">
      <skipped message="test fails if there is a module reload between collection and execution, as it breaks isinstance() inside __eq__()" type="pytest.skip">test_taskrunnerlib.py:211: test fails if there is a module reload between collection and execution, as it breaks isinstance() inside __eq__()</skipped>
    </testcase>
  </testsuite>
</testsuites>
'''.lstrip()

    report = parseReport(lambda: StringIO(xml), 'report.xml')
    assert report is not None

    assert report.errors == 0
    assert report.failures == 0
    assert report.skipped == 1
    assert report.numTestcases == 3
    # TODO: Giving skip priority over pass is probably not what users expect.
    #       Unexpected skips are worth highlighting and for jobs/tasks all
    #       skips are unexpected. But for test suites, skips are often known
    #       and should not grab attention.
    assert report.result is ResultCode.CANCELLED
    assert report.summary == '0 failed, 1 skipped'
    data = report.data
    assert data['testcases'] == '3'
    assert data['checks'] == '3'
    assert data['failures'] == '0'
    assert data['errors'] == '0'
    assert data['skipped'] == '1'

    assert len(report.testsuite) == 1
    suite, = report.testsuite
    assert suite.tests == 3
    assert suite.failures == 0
    assert suite.errors == 0
    assert suite.skipped == 1
    assert suite.time == 1.234
    assert suite.result is ResultCode.CANCELLED

    assert len(suite.testcase) == 3
    for index, case in enumerate(suite.testcase):
        if index == 2:
            assert case.result is ResultCode.CANCELLED
            assert case.skipped
        else:
            assert case.result is ResultCode.OK
            assert not case.skipped
        assert not case.error
        assert not case.failure

# SPDX-License-Identifier: BSD-3-Clause

"""Test result storage and processing functionality."""

from pytest import fixture, raises

from softfab.resultlib import ResultStorage


@fixture
def resultStorage(tmp_path):
    return ResultStorage(tmp_path)

# Test data that can be used by various test cases:
TASK_NAME = 'testtask'
RUN_ID = 'faster'
KEY = 'dawn'
NR_RUNS = 50

def testResultsPutGet(resultStorage):
    """Test whether data can be stored and retrieved."""

    def valueFunc(index):
        return f'value{index:02d}'

    runIds = []
    for index in range(NR_RUNS):
        runId = f'run{index:02d}'
        runIds.append(runId)
        data = {KEY: valueFunc(index)}
        resultStorage.putData(TASK_NAME, runId, data)

    results = resultStorage.getCustomData(TASK_NAME, runIds, KEY)
    foundIds = []
    for runId, value in results:
        assert runId.startswith('run')
        index = int(runId[3:])
        assert 0 <= index < NR_RUNS
        assert value == valueFunc(index)
        foundIds.append(runId)
    assert sorted(foundIds) == sorted(runIds)

def testResultsInvalidKey(resultStorage):
    """Test treatment of invalid keys."""

    # TODO: Maybe we need more thought about what should be valid keys.
    for key in ('../abc', ''):
        data = {key: 'dummy'}
        with raises(KeyError):
            resultStorage.putData(TASK_NAME, RUN_ID, data)
        results = resultStorage.getCustomData(TASK_NAME, [RUN_ID], key)
        assert list(results) == []

def testResultsReplace(resultStorage):
    """Check that new data replaces old data."""

    oldData = {KEY: 'old'}
    newData = {KEY: 'new'}
    resultStorage.putData(TASK_NAME, RUN_ID, oldData)
    resultStorage.putData(TASK_NAME, RUN_ID, newData)
    results = resultStorage.getCustomData(TASK_NAME, [RUN_ID], KEY)
    assert list(results) == [(RUN_ID, 'new')]

def testResultsAdd(resultStorage):
    """Check that new data with different keys is added to old data."""

    oldData = {'oldkey': 'old'}
    newData = {'newkey': 'new'}
    resultStorage.putData(TASK_NAME, RUN_ID, oldData)
    resultStorage.putData(TASK_NAME, RUN_ID, newData)
    results1 = resultStorage.getCustomData(TASK_NAME, [RUN_ID], 'oldkey')
    assert list(results1) == [(RUN_ID, 'old')]
    results2 = resultStorage.getCustomData(TASK_NAME, [RUN_ID], 'newkey')
    assert list(results2) == [(RUN_ID, 'new')]

def testResultsListKeys(resultStorage):
    """Tests listing the keys that exist for a task name."""

    for index in range(2, NR_RUNS):
        runId = f'run{index:02d}'
        keys = [
            f'key{key:02d}'
            for key in range(2, NR_RUNS)
            if key % index == 0
            ]
        data = dict.fromkeys(keys, 'dummy')
        resultStorage.putData(TASK_NAME, runId, data)

    assert resultStorage.getCustomKeys(TASK_NAME) == {
        # for every N, N % N == 0 is true
        # so every key for 2 <= key < nrRuns should be present
        f'key{key:02d}' for key in range(2, NR_RUNS)
        }

def testResultsListKeysNone(resultStorage):
    """Tests listing the keys if no data is stored for a task name."""

    assert resultStorage.getCustomKeys(TASK_NAME) == set()

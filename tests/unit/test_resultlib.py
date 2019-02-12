# SPDX-License-Identifier: BSD-3-Clause

import os, unittest

from initconfig import config

from datageneratorlib import removeRec

from softfab import resultlib

class TestResults(unittest.TestCase):
    """Test result storage and processing functionality.
    """

    # Test data that can be used by various test cases:
    taskName = 'testtask'
    runId = 'faster'
    key = 'dawn'
    nrRuns = 50
    @staticmethod
    def valueFunc(index):
        return 'value%02d' % index

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)

    def setUp(self):
        pass

    def tearDown(self):
        removeRec(config.dbDir)

    def test0010PutGet(self):
        "Test whether data can be stored and retrieved."

        runIds = []
        for index in range(self.nrRuns):
            runId = 'run%02d' % index
            runIds.append(runId)
            data = { self.key: self.valueFunc(index) }
            resultlib.putData(self.taskName, runId, data)

        results = resultlib.getData(self.taskName, runIds, self.key)
        foundIds = []
        for runId, value in results:
            self.assertTrue(runId.startswith('run'))
            index = int(runId[3:])
            self.assertTrue(0 <= index < self.nrRuns)
            self.assertEqual(value, self.valueFunc(index))
            foundIds.append(runId)
        self.assertEqual(sorted(foundIds), sorted(runIds))

    def test0020InvalidKey(self):
        "Test treatment of invalid keys."

        # TODO: Maybe we need more thought about what should be valid keys.
        for key in ( '../abc', '' ):
            data = { key: 'dummy' }
            self.assertRaises(
                KeyError,
                lambda: resultlib.putData(self.taskName, self.runId, data)
                )
            results = resultlib.getData(self.taskName, [ self.runId ], key)
            self.assertEqual(list(results), [])

        # This test case is atypical by not storing anything.
        # Make sure removeRec doesn't complain that the dir does not exist.
        os.makedirs(config.dbDir)

    def test0030Replace(self):
        "Check that new data replaces old data."

        oldData = { self.key: 'old' }
        newData = { self.key: 'new' }
        resultlib.putData(self.taskName, self.runId, oldData)
        resultlib.putData(self.taskName, self.runId, newData)
        results = resultlib.getData(self.taskName, [ self.runId ], self.key)
        self.assertEqual(list(results), [ ( self.runId, 'new' ) ])

    def test0031ReplaceDiffKeys(self):
        "Check that new data with different keys removes old keys."

        oldData = { 'oldkey': 'old' }
        newData = { 'newkey': 'new' }
        resultlib.putData(self.taskName, self.runId, oldData)
        resultlib.putData(self.taskName, self.runId, newData)
        results1 = resultlib.getData(self.taskName, [ self.runId ], 'oldkey')
        self.assertEqual(list(results1), [ ])
        results2 = resultlib.getData(self.taskName, [ self.runId ], 'newkey')
        self.assertEqual(list(results2), [ ( self.runId, 'new' ) ])

    def test0040ListKeys(self):
        "Tests listing the keys that exist for a task name."

        for index in range(2, self.nrRuns):
            runId = 'run%02d' % index
            keys = [
                'key%02d' % key
                for key in range(2, self.nrRuns)
                if key % index == 0
                ]
            data = dict.fromkeys(keys, 'dummy')
            resultlib.putData(self.taskName, runId, data)

        storedKeys = resultlib.getKeys(self.taskName)
        storedKeys.difference_update(resultlib.syntheticKeys)
        self.assertEqual(
            storedKeys,
            # for every N, N % N == 0 is true
            # so every key for 2 <= key < nrRuns should be present
            set( 'key%02d' % key for key in range(2, self.nrRuns) )
            )

    def test0041ListKeysNone(self):
        "Tests listing the keys if no data is stored for a task name."

        self.assertEqual(
            list(resultlib.getKeys(self.taskName)),
            list(resultlib.syntheticKeys)
            )

        # This test case is atypical by not storing anything.
        # Make sure removeRec doesn't complain that the dir does not exist.
        os.makedirs(config.dbDir)

if __name__ == '__main__':
    unittest.main()

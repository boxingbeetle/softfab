# SPDX-License-Identifier: BSD-3-Clause

import os, os.path, unittest
from importlib import reload

from softfab import config
config.dbDir = 'testdb'
assert not os.path.exists(config.dbDir)

from softfab import databases, resourcelib, shadowlib
from softfab.resultcode import ResultCode

import shadowtestutils
from datageneratorlib import DataGenerator, removeRec

class TestResults(unittest.TestCase):
    """Test shadow queue management.
    """

    # Test data that can be used by various test cases:

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)

    def setUp(self):
        databases.reloadDatabases()
        reload(shadowtestutils)

    def tearDown(self):
        removeRec(config.dbDir)

    def createRun(self):
        run = shadowtestutils.TestShadowRun.create()
        shadowlib.shadowDB.add(run)
        return run

    def createAssignedRun(self):
        run = self.createRun()
        gen = DataGenerator()
        taskRunnerId = gen.createTaskRunner(name='capable')
        taskRunner = resourcelib.resourceDB[taskRunnerId]
        assigned = run.assign(taskRunner)
        self.assertTrue(assigned)
        return run, taskRunner

    def checkWaiting(self, run):
        self.assertTrue(run.isWaiting())
        self.assertTrue(not run.isRunning())
        self.assertEqual(run.getResult(), None)
        self.assertEqual(run.getTaskRunnerId(), None)

    def checkRunning(self, run, taskRunner):
        self.assertTrue(not run.isWaiting())
        self.assertTrue(run.isRunning())
        self.assertEqual(run.getResult(), None)
        self.assertEqual(run.getTaskRunnerId(), taskRunner.getId())

    def checkDone(self, run, taskRunner, result):
        self.assertTrue(not run.isWaiting())
        self.assertTrue(not run.isRunning())
        self.assertEqual(run.getResult(), result)
        self.assertEqual(run.getTaskRunnerId(), taskRunner.getId())

    # TODO: Write tests for record listeners.

    def test0010New(self):
        "Test whether a new shadow run can be created and has the right state."
        run = self.createRun()
        self.checkWaiting(run)

    def test0020Assign(self):
        "Test assigning to a capable Task Runner."
        run, taskRunner = self.createAssignedRun()
        self.checkRunning(run, taskRunner)

    def test0021AssignFail(self):
        "Test assigning to an incapable Task Runner."
        run = self.createRun()
        gen = DataGenerator()
        taskRunnerId = gen.createTaskRunner(name='incapable')
        taskRunner = resourcelib.resourceDB[taskRunnerId]
        assigned = run.assign(taskRunner)
        self.assertTrue(not assigned)
        self.checkWaiting(run)

    def test0030DoneNeverStarted(self):
        "Test what happens if a run that was never started is marked as done."
        run = self.createRun()
        run.done(ResultCode.OK)
        self.checkWaiting(run)

    def test0031DoneInvalidResult(self):
        "Test handling of an invalid result code."
        run, taskRunner = self.createAssignedRun()
        self.assertRaises(
            ValueError,
            lambda: run.done('this-is-not-a-valid-result-code')
            )
        self.checkRunning(run, taskRunner)
        self.assertRaises(
            ValueError,
            lambda: run.done(ResultCode.CANCELLED)
            )
        self.checkRunning(run, taskRunner)

    def test0032DoneOK(self):
        "Test handling of a run that ends with result 'ok'."
        run, taskRunner = self.createAssignedRun()
        run.done(ResultCode.OK)
        self.checkDone(run, taskRunner, ResultCode.OK)

    def test0033DoneWarning(self):
        "Test handling of a run that ends with result 'warning'."
        run, taskRunner = self.createAssignedRun()
        run.done(ResultCode.WARNING)
        self.checkDone(run, taskRunner, ResultCode.WARNING)

    def test0034DoneError(self):
        "Test handling of a run that ends with result 'error'."
        run, taskRunner = self.createAssignedRun()
        run.done(ResultCode.ERROR)
        self.checkDone(run, taskRunner, ResultCode.ERROR)

    def test0035DoneTwiceOK(self):
        "Mark a task as 'ok' and then mark it again, as 'warning'."
        run, taskRunner = self.createAssignedRun()
        run.done(ResultCode.OK)
        run.done(ResultCode.WARNING)
        self.checkDone(run, taskRunner, ResultCode.OK)

    def test0036DoneTwiceWarning(self):
        "Mark a task as 'warning' and then mark it again, as 'ok'."
        run, taskRunner = self.createAssignedRun()
        run.done(ResultCode.WARNING)
        run.done(ResultCode.OK)
        self.checkDone(run, taskRunner, ResultCode.WARNING)

    def test0040URL(self):
        "Test storing of logging URL."
        run = self.createRun()
        self.assertEqual(run.getURL(), None)
        url = 'http://host/path/log.txt'
        run.setURL(url)
        self.assertEqual(run.getURL(), url)

if __name__ == '__main__':
    unittest.main()

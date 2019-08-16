# SPDX-License-Identifier: BSD-3-Clause

"""Tests the parts of the resourcelib module that are not tested by the
test_resource_requirements suite.
"""

import unittest

from initconfig import config

from softfab import databases, resourcelib

from datageneratorlib import removeRec

def resourcesOfType(typeName):
    return sorted(resourcelib.resourceDB.resourcesOfType(typeName))

class TestResources(unittest.TestCase):
    """Test resources."""

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)

    def reloadDatabases(self):
        databases.reloadDatabases()

    def setUp(self):
        self.reloadDatabases()

    def tearDown(self):
        removeRec(config.dbDir)

    def test0100ResourcesOfType(self):
        """Test resourceDB.resourcesOfType() method."""

        res1 = resourcelib.Resource.create('R1', 'TA', '', '', ())
        res2 = resourcelib.Resource.create('R2', 'TA', '', '', ())
        res3 = resourcelib.Resource.create('R3', 'TB', '', '', ())
        res4 = resourcelib.Resource.create('R4', 'TB', '', '', ())

        # DB is empty.
        self.assertEqual(resourcesOfType('TA'), [])
        self.assertEqual(resourcesOfType('TB'), [])

        # Add records.
        resourcelib.resourceDB.add(res1)
        self.assertEqual(resourcesOfType('TA'), ['R1'])
        self.assertEqual(resourcesOfType('TB'), [])
        resourcelib.resourceDB.add(res4)
        self.assertEqual(resourcesOfType('TA'), ['R1'])
        self.assertEqual(resourcesOfType('TB'), ['R4'])
        resourcelib.resourceDB.add(res3)
        self.assertEqual(resourcesOfType('TA'), ['R1'])
        self.assertEqual(resourcesOfType('TB'), ['R3', 'R4'])
        resourcelib.resourceDB.add(res2)
        self.assertEqual(resourcesOfType('TA'), ['R1', 'R2'])
        self.assertEqual(resourcesOfType('TB'), ['R3', 'R4'])

        # Remove record.
        resourcelib.resourceDB.remove(res4)
        self.assertEqual(resourcesOfType('TA'), ['R1', 'R2'])
        self.assertEqual(resourcesOfType('TB'), ['R3'])

        # Change type of record.
        res1Bv2 = resourcelib.Resource.create('R2', 'TB', '', '', ())
        resourcelib.resourceDB.update(res1Bv2)
        self.assertEqual(resourcesOfType('TA'), ['R1'])
        self.assertEqual(resourcesOfType('TB'), ['R2', 'R3'])

        self.reloadDatabases()
        self.assertEqual(resourcesOfType('TA'), ['R1'])
        self.assertEqual(resourcesOfType('TB'), ['R2', 'R3'])

if __name__ == '__main__':
    unittest.main()

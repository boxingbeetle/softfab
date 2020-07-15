# SPDX-License-Identifier: BSD-3-Clause

"""Tests the parts of the resourcelib module that are not tested by the
test_resource_requirements suite.
"""

import unittest

from initconfig import removeDB

from softfab import databases, resourcelib


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
        removeDB()

    def test0100ResourcesOfType(self):
        """Test resourceDB.resourcesOfType() method."""

        resourceFactory = resourcelib.resourceDB.factory
        res1 = resourceFactory.newResource('R1', 'TA', '', ())
        res2 = resourceFactory.newResource('R2', 'TA', '', ())
        res3 = resourceFactory.newResource('R3', 'TB', '', ())
        res4 = resourceFactory.newResource('R4', 'TB', '', ())

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
        res1Bv2 = resourceFactory.newResource('R2', 'TB', '', ())
        resourcelib.resourceDB.update(res1Bv2)
        self.assertEqual(resourcesOfType('TA'), ['R1'])
        self.assertEqual(resourcesOfType('TB'), ['R2', 'R3'])

        self.reloadDatabases()
        self.assertEqual(resourcesOfType('TA'), ['R1'])
        self.assertEqual(resourcesOfType('TB'), ['R2', 'R3'])

if __name__ == '__main__':
    unittest.main()

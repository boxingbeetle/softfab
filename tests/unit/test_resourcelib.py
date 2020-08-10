# SPDX-License-Identifier: BSD-3-Clause

"""Tests the parts of the resourcelib module that are not tested by the
test_resource_requirements suite.
"""

# Import for the side effect of setting dbDir.
# We're not going to use that dir, but resourcelib still needs it.
import initconfig

from softfab.resourcelib import ResourceDB


def testResourcesOfType(tmp_path):
    """Test ResourceDB.resourcesOfType() method."""

    def createDB():
        resourceDB = ResourceDB(tmp_path)
        resourceDB.factory.resTypeDB = None
        resourceDB.preload()
        return resourceDB

    def resourcesOfType(typeName):
        return sorted(resourceDB.resourcesOfType(typeName))

    resourceDB = createDB()

    res1 = resourceDB.factory.newResource('R1', 'TA', '', ())
    res2 = resourceDB.factory.newResource('R2', 'TA', '', ())
    res3 = resourceDB.factory.newResource('R3', 'TB', '', ())
    res4 = resourceDB.factory.newResource('R4', 'TB', '', ())

    # DB is empty.
    assert resourcesOfType('TA') == []
    assert resourcesOfType('TB') == []

    # Add records.
    resourceDB.add(res1)
    assert resourcesOfType('TA') == ['R1']
    assert resourcesOfType('TB') == []
    resourceDB.add(res4)
    assert resourcesOfType('TA') == ['R1']
    assert resourcesOfType('TB') == ['R4']
    resourceDB.add(res3)
    assert resourcesOfType('TA') == ['R1']
    assert resourcesOfType('TB') == ['R3', 'R4']
    resourceDB.add(res2)
    assert resourcesOfType('TA') == ['R1', 'R2']
    assert resourcesOfType('TB') == ['R3', 'R4']

    # Remove record.
    resourceDB.remove(res4)
    assert resourcesOfType('TA') == ['R1', 'R2']
    assert resourcesOfType('TB') == ['R3']

    # Change type of record.
    res1Bv2 = resourceDB.factory.newResource('R2', 'TB', '', ())
    resourceDB.update(res1Bv2)
    assert resourcesOfType('TA') == ['R1']
    assert resourcesOfType('TB') == ['R2', 'R3']

    # Reload DB.
    resourceDB = createDB()
    assert resourcesOfType('TA') == ['R1']
    assert resourcesOfType('TB') == ['R2', 'R3']

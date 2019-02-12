# SPDX-License-Identifier: BSD-3-Clause

import time
import unittest
from collections import defaultdict
from random import Random

from softfab.connection import ConnectionStatus
from softfab.dispatchlib import pickResources
from softfab.resreq import ResourceClaim, ResourceSpec

sequenceNr = 0

class FakeResource:
    connectionStatus = ConnectionStatus.CONNECTED
    reserved = False
    suspended = False

    def __init__(self, typeName, capabilities):
        global sequenceNr
        sequenceNr += 1
        resId = 'res%d' % sequenceNr
        self.__resId = resId
        self.typeName = typeName
        self.capabilities = frozenset(capabilities)

    def __repr__(self):
        return 'FakeResource(%s, %s)@%s' % (
            self.typeName, self.capabilities, self.__resId
            )

    def getId(self):
        return self.__resId

    @property
    def cost(self):
        return len(self.capabilities)

    def getConnectionStatus(self):
        return self.connectionStatus

    def isReserved(self):
        return self.reserved

    def isSuspended(self):
        return self.suspended

def hasSolution(claim, resMap):
    """Computes whether a resource allocation exists that satisfies `claim`
    using resources from `resMap`.
    Assumes that all specs in `claim` and all resources in `resMap` use the
    same resource type.
    Returns True iff allocation is possible.
    """

    # Use Hall's marriage theorem to check whether a solution exists,
    # without having to compute a solution.
    # https://en.wikipedia.org/wiki/Hall%27s_marriage_theorem

    resMatchingSpec = [set() for spec in claim]
    for resId, resource in resMap.items():
        capabilities = resource.capabilities
        for specIdx, spec in enumerate(claim):
            if spec.capabilities.issubset(capabilities):
                resMatchingSpec[specIdx].add(resId)

    for specBits in range(1 << len(claim)):
        matchingResources = set()
        numSpecs = 0
        for resources in applyBitmask(resMatchingSpec, specBits):
            matchingResources |= resources
            numSpecs += 1
        if numSpecs > len(matchingResources):
            return False
    else:
        return True

def minimalCost(claim, resMap):
    """Computes the lowest possible cost for a resource allocation.
    It uses a slow but simple search, which should handle small cases
    just fine, but is not suitable for large cases.
    All resources in `resMap` must be in an available state.
    Returns None if no allocation is possible, otherwise the minimum
    total cost (sum).
    """
    claimedTypes = set(spec.typeName for spec in claim)
    specsByType = {
        typeName: tuple(claim.iterSpecsOfType(typeName))
        for typeName in claimedTypes
        }
    resourcesByType = defaultdict(set)
    for resId, resource in resMap.items():
        resourcesByType[resource.typeName].add(resId)

    # A rough indication of how long we're going to take to compute all
    # possible allocations for the given resource type.
    def effort(typeName):
        return len(specsByType[typeName]) * len(resourcesByType[typeName])

    # Start with the lowest-effort computations, because if those do not
    # produce a match, we save time by not running the high-effort ones.
    totalCost = 0
    for typeName in sorted(claimedTypes, key=effort):
        cost = _minimalCostType(
            specsByType[typeName], resourcesByType[typeName], resMap
            )
        if cost is None:
            return None
        else:
            totalCost += cost
    return totalCost

def _minimalCostType(specs, resIds, resMap):
    """Helper function for `minimalCost`.
    All given specs and resources must be of the same type.
    """

    # Precalculations to speed up recursive search.
    numSpecs = len(specs)
    costs = []
    resMatchingSpec = [[] for spec in specs]
    for resIdx, resId in enumerate(resIds):
        resource = resMap[resId]
        costs.append(resource.cost)
        capabilities = resource.capabilities
        for specIdx, spec in enumerate(specs):
            if spec.capabilities.issubset(capabilities):
                resMatchingSpec[specIdx].append(resIdx)

    # Note specIdx is equal to the number of bits reset in availableIds,
    # so we don't need to include it separately in the cache key.
    cache = {}
    def solve(specIdx, availableIds):
        if specIdx == numSpecs:
            return 0
        minCost = cache.get(availableIds)
        if minCost is not None:
            return minCost
        for resIdx in resMatchingSpec[specIdx]:
            mask = 1 << resIdx
            if availableIds & mask:
                remIds = availableIds & ~mask
                remCost = solve(specIdx + 1, remIds)
                if remCost is not None:
                    cost = remCost + costs[resIdx]
                    if minCost is None or cost < minCost:
                        minCost = cost
        cache[availableIds] = minCost
        return minCost
    return solve(0, (1 << len(resIds)) - 1)

def applyBitmask(sequence, bitmask):
    """Iterate through those items in `sequence` of which the bit corresponding
    to their index is set in `bitmask`.
    """
    for i in range(bitmask.bit_length()):
        if (bitmask >> i) & 1:
            yield sequence[i]

def simulateRandom(maxCaps, maxSpecs, maxResources, runsPerConfig, numConfigs,
        verifyFunc, seed=None):
    if seed is None:
        seed = int(time.time())
    print('Random seed: %d' % seed)
    rnd = Random(seed)

    # Pre-create capability and reference names.
    caps = tuple('cap%d' % i for i in range(maxCaps))
    refs = tuple('ref%d' % i for i in range(maxSpecs))

    for _ in range(numConfigs):
        numCaps = rnd.randint(maxCaps // 2, maxCaps)
        numResources = rnd.randint(maxResources // 2, maxResources)

        # Create resources.
        resMap = {}
        for _ in range(numResources):
            capBits = rnd.randrange(1 << numCaps)
            resource = FakeResource('typeA', applyBitmask(caps, capBits))
            resMap[resource.getId()] = resource

        for _ in range(runsPerConfig):
            numSpecs = rnd.randint(maxSpecs // 2, maxSpecs)

            # Create specs.
            specs = []
            for i in range(numSpecs):
                # Create a slight bias towards having fewer capabilities
                # required, so we test finding the lowest cost assignment
                # among multiple possible ones.
                capBits = rnd.randrange(1 << numCaps)
                capBits &= rnd.randrange(1 << numCaps)
                spec = ResourceSpec.create(
                    refs[i], 'typeA', applyBitmask(caps, capBits)
                    )
                specs.append(spec)

            claim = ResourceClaim.create(specs)
            verifyFunc(claim, resMap)

class TestResourceMatching(unittest.TestCase):
    """Test matching resource requirements to resources.
    """

    def check(self, claim, resources, expected):
        """Compares the match result against an expected value."""
        resMap = {res.getId(): res for res in resources}

        # Without reason-for-waiting.
        match = pickResources(claim, resMap)
        self.assertEqual(match, expected)

        # With reason-for-waiting.
        whyNot = []
        match = pickResources(claim, resMap, whyNot)
        self.assertEqual(match, expected)
        if expected is None:
            self.assertNotEqual(whyNot, [])
        else:
            self.assertEqual(whyNot, [])

    def checkAssignment(self, claim, assignment):
        """Checks whether `assignment` matches `claim`.
        """
        # Assigned references must match the claim's specs one-to-one.
        self.assertCountEqual(
            (spec.reference for spec in claim),
            assignment.keys()
            )

        # Check whether each assigned resource matches its spec.
        for spec in claim:
            assigned = assignment[spec.reference]
            self.assertEqual(spec.typeName, assigned.typeName)
            self.assertTrue(spec.capabilities.issubset(assigned.capabilities))

        # Check whether all assigned resources are unique.
        usedIds = set()
        for resource in assignment.values():
            resId = resource.getId()
            self.assertNotIn(resId, usedIds)
            usedIds.add(resId)

        # Check whether all assigned resources are available.
        for resource in assignment.values():
            self.assertFalse(resource.isReserved())
            self.assertFalse(resource.isSuspended())
            self.assertEqual(
                resource.getConnectionStatus(), ConnectionStatus.CONNECTED
                )

    def checkSolve(self, claim, resMap):
        """Check dispatchlib's resource pick by comparing it to the results
        of our slow but simple reference implementation.
        """
        match = pickResources(claim, resMap)
        if match is not None:
            self.checkAssignment(claim, match)

        # Reason-for-waiting computations should not change which reservation
        # is picked.
        whyNot = []
        match2 = pickResources(claim, resMap, whyNot)
        self.assertEqual(match, match2)

        minCost = minimalCost(claim, resMap)
        if minCost is None:
            self.assertIsNone(match)
            self.assertNotEqual(len(whyNot), 0)
        else:
            self.assertIsNotNone(match)
            self.assertEqual(len(whyNot), 0)
            # Since checkAssignment() already verified that the pick is valid,
            # all we have to do is check that it also has minimal cost.
            cost = sum(res.cost for res in match.values())
            self.assertEqual(cost, minCost)

    def checkValid(self, claim, resMap):
        """Check dispatchlib's resource pick by applying sanity checks to it.
        This is less thorough than `checkSolve`, but a lot faster.
        """
        match = pickResources(claim, resMap)
        if match is None:
            self.assertFalse(hasSolution(claim, resMap))
        else:
            # Note: checkAssignment() is much faster than hasSolution()
            #       and if it doesn't find problems in the assignment then
            #       it is also established that a solution is possible.
            #       The only reason to call hasSolution() is to test that
            #       function itself, but we don't need to do that unless
            #       we're working on the unit test.
            #self.assertTrue(hasSolution(claim, resMap))
            self.checkAssignment(claim, match)

    def test0100NoResources(self):
        """Test making a match without resources."""
        claim = ResourceClaim.create((
            ResourceSpec.create('ref0', 'typeA', ()),
            ))

        self.check(claim, (), None)

    def test0110NoClaim(self):
        """Test making a match without a claim."""
        claim = ResourceClaim.create(())

        self.check(claim, (), {})

    def test0200OneResourcePossible(self):
        """Test making a possible match with one resource."""
        claim = ResourceClaim.create((
            ResourceSpec.create('ref0', 'typeA', ()),
            ))
        res = FakeResource('typeA', ())
        resources = (res,)

        expected = {'ref0': res}

        self.check(claim, resources, expected)

    def test0210OneResourceImpossible(self):
        """Test making a impossible match with one resource."""
        claim = ResourceClaim.create((
            ResourceSpec.create('ref0', 'typeA', ()),
            ))
        res = FakeResource('typeB', ())
        resources = (res,)

        self.check(claim, resources, None)

    def test0300TwoResourcesDiffTypes(self):
        """Test making a match with two resources of different types."""
        claim = ResourceClaim.create((
            ResourceSpec.create('ref0', 'typeA', ()),
            ResourceSpec.create('ref1', 'typeB', ()),
            ))
        resA = FakeResource('typeA', ())
        resB = FakeResource('typeB', ())
        resources = (resA, resB)

        expected = {'ref0': resA, 'ref1': resB}

        self.check(claim, resources, expected)

    def test0310TwoResourcesSameType(self):
        """Test making a match with two resources of the same types."""
        claim = ResourceClaim.create((
            ResourceSpec.create('ref0', 'typeA', ()),
            ResourceSpec.create('ref1', 'typeA', ()),
            ))
        resA = FakeResource('typeA', ())
        resB = FakeResource('typeA', ())
        resources = (resA, resB)

        resMap = {res.getId(): res for res in resources}
        match = pickResources(claim, resMap)
        self.assertIsNotNone(match)

    def test0320TwoResourcesUniqueCaps(self):
        """Test making a match with two resources with unique capabilities."""
        claim = ResourceClaim.create((
            ResourceSpec.create('ref0', 'typeA', ('capY',)),
            ResourceSpec.create('ref1', 'typeA', ('capX',)),
            ))
        resX = FakeResource('typeA', ('capX',))
        resY = FakeResource('typeA', ('capY',))
        resources = (resX, resY)

        expected = {'ref0': resY, 'ref1': resX}

        self.check(claim, resources, expected)

    def test0400OverlappingCaps(self):
        """Test making a match with overlapping capabilities."""
        claim = ResourceClaim.create((
            ResourceSpec.create('ref2', 'typeA', ('capY',)),
            ResourceSpec.create('ref0', 'typeA', ('capW',)),
            ResourceSpec.create('ref1', 'typeA', ('capX',)),
            ResourceSpec.create('ref3', 'typeA', ('capZ',)),
            ))
        resW = FakeResource('typeA', ('capW',))
        resX = FakeResource('typeA', ('capW', 'capX'))
        resY = FakeResource('typeA', ('capW', 'capX', 'capY'))
        resZ = FakeResource('typeA', ('capW', 'capX', 'capY', 'capZ'))
        resources = (resW, resX, resY, resZ)

        expected = {'ref0': resW, 'ref1': resX, 'ref2': resY, 'ref3': resZ}

        self.check(claim, resources, expected)

    def test0410UnequalValue(self):
        """Test making a match with two resources with differing value.
        A resource without capabilities should be picked before resources
        with capabilities.
        """
        claim = ResourceClaim.create((
            ResourceSpec.create('ref0', 'typeA', ()),
            ))
        resources = []
        for _ in range(50):
            resources.append(FakeResource('typeA', ('capX',)))
        resNoCaps = FakeResource('typeA', ())
        resources[29] = resNoCaps

        expected = {'ref0': resNoCaps}

        self.check(claim, resources, expected)

    def test0420MissingType(self):
        """Test a claim that can be honored for one type but not for another.
        """
        claim = ResourceClaim.create((
            ResourceSpec.create('ref%d' % i, 'typeA', ('cap%d' % (i % 4),))
            for i in range(10)
            ))
        resources = []
        for i in range(24):
            resources.append(FakeResource('typeA', ('cap%d' % (i % 4),)))

        # Sanity check for our test data.
        resMap = {res.getId(): res for res in resources}
        match = pickResources(claim, resMap)
        self.assertIsNotNone(match)

        claim = claim.merge(ResourceClaim.create((
            ResourceSpec.create('refB', 'typeB', ('cap0',)),
            )))
        self.check(claim, resources, None)

    def test1000AllCombinations(self):
        """Test all possible claims on all possible resources, at small size.
        It is feasible to do this for low numbers of claims, capabilities and
        resources, but it becomes expotentially slower at larger sizes.
        """
        numCaps = 3
        numSpecs = 3
        numResources = 3

        caps = tuple('cap%d' % i for i in range(numCaps))
        refs = tuple('ref%d' % i for i in range(numSpecs))

        claims = tuple(
            ResourceClaim.create((
                ResourceSpec.create(refs[i], 'typeA', (
                    caps[j]
                    for j in range(numCaps)
                    if (claimBits >> (i * numCaps + j)) & 1
                    ))
                for i in range(numSpecs)
                ))
            for claimBits in range(1 << (numSpecs * numCaps))
            )

        resourceMaps = []
        for resBits in range(1 << (numResources * numCaps)):
            resources = [
                FakeResource('typeA', (
                    caps[j]
                    for j in range(numCaps)
                    if (resBits >> (i * numCaps + j)) & 1
                    ))
                for i in range(numResources)
                ]
            resourceMaps.append({res.getId(): res for res in resources})

        for claim in claims:
            for resMap in resourceMaps:
                self.checkSolve(claim, resMap)

    def test1100RandomMedium(self):
        """Test randomly generated medium-size claims.
        At medium size, we can use the `minimalCost` function to verify that
        the assignment produced by `dispatchlib` is indeed of minimal cost.
        """
        simulateRandom(
            maxCaps=6,
            maxSpecs=5,
            maxResources=15,
            runsPerConfig=100,
            numConfigs=100,
            verifyFunc=self.checkSolve,
            seed=int(time.time())
            )

    def test1200RandomLarge(self):
        """Test randomly generated large-size claims.
        At large size, we have no way to verify that a found assignment is
        of minimal cost, but we can still verify whether it is valid.
        """
        simulateRandom(
            maxCaps=8,
            maxSpecs=12,
            maxResources=100,
            runsPerConfig=100,
            numConfigs=100,
            verifyFunc=self.checkValid,
            seed=int(time.time())
            )

if __name__ == '__main__':
    unittest.main()

# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from typing import (
    Dict, Iterable, List, Mapping, Optional, Sequence, Set,
    cast, overload
    )

from resreq import ResourceClaim, ResourceSpec
from resourcelib import Resource
from waiting import (
    ReasonForWaiting, ResourceCapsReason, ResourceSpecReason,
    ResourceTypeReason, StatusLevel, statusLevelForResource
    )

@overload
def _groupByType(
        items: Iterable[Resource] # pylint: disable=unused-argument
        ) -> Mapping[str, Sequence[Resource]]:
    pass
@overload
def _groupByType(
        items: Iterable[ResourceSpec] # pylint: disable=unused-argument
        ) -> Mapping[str, Sequence[ResourceSpec]]:
    pass
def _groupByType(items):
    grouped = defaultdict(list)
    for item in items:
        grouped[item.typeName].append(item)
    return grouped

def findMatch(matrix: List[List[int]]) -> Optional[List[int]]:
    """Finds a minimum cost assignment for the given cost `matrix`.
    The `matrix` will be modified by this function in an unspecified way.
    Returns the assignment as a list in which item N is the number of the
    column assigned for row N, or None if no assignment is possible.
    """

    # Use the Hungarian Algorithm (Munkres, Kuhn).
    #
    # This particular implementation is based on the book "Parallel Computing
    # Works" by Geoffrey C. Fox, Roy D. Williams and Paul C. Messina.
    # http://www.netlib.org/utk/lsi/pcwLSI/text/node222.html
    #
    # The difference between the book's version of the algorithm and most
    # versions found online is that it doesn't require a square matrix,
    # which is useful in our case since we'll usually have more resources
    # than specs. It is possible to pad a non-square matrix with rows of
    # zeroes, but that slows down execution significantly.
    # Also the book formally describes every necessary step, unlike a lot of
    # other descriptions of the algorithm that are vague about how to generate
    # a minimal covering.
    #
    # Compared to the book's version, I exchanged rows and columns, because
    # it fits our use case better.

    numRows = len(matrix)
    numCols = len(matrix[0])
    if numRows > numCols:
        # More requirements than resources: assignment is impossible.
        return None

    # Step 0: Row reduction.
    # We have to pick a resource for each spec, so as long as the relative
    # costs remain the same, the same assignments remain optimal.
    # By subtracting the minimum cost of the row, we create more zeroes.
    for row in matrix:
        minVal = min(row)
        if minVal != 0:
            assert minVal > 0
            for ci in range(numCols):
                row[ci] -= minVal

    # Step 1: Perform greedy assignments as a starting point.
    # More sophisticated algorithms can be used for the initial assignments,
    # but in my experiments the time won by having fewer refinement iterations
    # (step 2-5) was roughly equal to the extra time spent in step 1.
    rowAssigned = [None] * numRows # type: List[Optional[int]]
    colAssigned = [None] * numCols # type: List[Optional[int]]
    for ri, row in enumerate(matrix):
        for ci in range(numCols):
            if row[ci] == 0 and colAssigned[ci] is None:
                rowAssigned[ri] = ci
                colAssigned[ci] = ri
                break

    reinit = True
    while True:
        if reinit:
            reinit = False

            # Step 2.1: Cover rows that contain an assignment.
            uncoveredRowIdxs = set(
                ri
                for ri, ci in enumerate(rowAssigned)
                if ci is None
                )
            # Step 2.2: Terminate when we have a full assignment.
            if not uncoveredRowIdxs:
                return cast(List[int], rowAssigned)

            uncoveredColIdxs = set(range(numCols))
            primed = [None] * numCols # type: List[Optional[int]]

        # Step 3: Search for uncovered zero.
        for ri, ci in (
                (ri, ci)
                for ri in uncoveredRowIdxs
                for ci in uncoveredColIdxs
                if matrix[ri][ci] == 0
                ):
            # Step 3.1: Found an uncovered zero, prime it.
            assert primed[ci] is None
            primed[ci] = ri
            # Look for assignment in the same column.
            assignedRI = colAssigned[ci]
            if assignedRI is None:
                # Step 4: Move assignments along a chain of zeroes.
                # The end result is one assignment more.
                while True:
                    nci = rowAssigned[ri]
                    rowAssigned[ri] = ci
                    colAssigned[ci] = ri
                    if nci is None:
                        break
                    ci = nci
                    ri = cast(int, primed[ci])
                # Continue at step 2.
                reinit = True
            else:
                # Step 3.3: Flip assignment's cover from row to column.
                # The new primed zero becomes covered.
                uncoveredRowIdxs.add(assignedRI)
                uncoveredColIdxs.remove(ci)
                # Continue at step 3.
            break
        else:
            # Step 5: No uncovered zeroes; create new ones.
            # Adding to double-covered cells and subtracting from uncovered
            # cells is equivalent to adding to covered columns and subtracting
            # from uncovered rows, but takes less effort.
            # Note that assigned zeroes are always single-covered, so this step
            # will not touch them.
            minVal = min(
                matrix[ri][ci]
                for ri in uncoveredRowIdxs
                for ci in uncoveredColIdxs
                )
            assert minVal > 0, minVal
            # Add minimum cost to all double-covered cells.
            coveredColIdxs = set(range(numCols)) - uncoveredColIdxs
            for ri, row in enumerate(matrix):
                if ri not in uncoveredRowIdxs:
                    for ci in coveredColIdxs:
                        row[ci] += minVal
            # Subtract minimum cost from all uncovered cells.
            for ri in uncoveredRowIdxs:
                row = matrix[ri]
                for ci in uncoveredColIdxs:
                    row[ci] -= minVal
            # Continue at step 3.

def pickResources(
        claim: ResourceClaim,
        resources: Mapping[str, Resource],
        whyNot: Optional[List[ReasonForWaiting]] = None
        ) -> Optional[Mapping[str, Resource]]:
    """Find a resource reservation that satisfies `claim`.
    Resources are picked from the `resources` mapping that must have resource
    IDs as keys and resources as values.
    Returns a mapping from resource reference to resource, or None if the
    claim cannot be satisfied.
    If `whyNot` was provided, reasons for not being able to find a resource
    assignment are appended to `whyNot`.
    """
    if whyNot is None:
        # We're only interested in finding a match on free resources.
        levels = (StatusLevel.FREE,) # type: Iterable[StatusLevel]
    else:
        # Start looking for a match using only free resources, but if we don't
        # find a match, add resources in other states, so we can report which
        # resource state is blocking progress.
        levels = StatusLevel.__members__.values()

    specsByType = _groupByType(claim)
    resourcesByType = _groupByType(resources.values())

    reservation = {} # type: Dict[str, Resource]
    for typeName, specs in specsByType.items():
        resourcesByLevel = defaultdict(list) \
            # type: Mapping[StatusLevel, List[Resource]]
        for res in resourcesByType[typeName]:
            level = statusLevelForResource(res)
            resourcesByLevel[level].append(res)

        capOfferedBy = defaultdict(set) # type: Mapping[str, Set[str]]
        resourceIds = []
        costs = {}
        for level in levels:
            # Skip this level if it doesn't add new resources.
            newResources = resourcesByLevel[level]
            if not newResources and level != StatusLevel.FREE:
                continue

            # Insert new resources.
            for res in newResources:
                resId = res.getId()
                resourceIds.append(resId)
                caps = res.capabilities
                costs[resId] = res.cost
                for cap in caps:
                    capOfferedBy[cap].add(resId)

            # Build a cost matrix.
            numRows = len(specs)
            numCols = len(resourceIds)
            if numRows > numCols:
                if whyNot is not None:
                    whyNot.append(
                        ResourceTypeReason(typeName, numRows - numCols, level)
                        )
                continue
            # Cells representing invalid assignments will be assigned a cost
            # that is always higher than any valid assignment.
            infinity = sum(costs.values()) + 1
            matrix = []
            for spec in specs:
                # Find the resources that match this spec.
                candidates = set(resourceIds)
                for cap in spec.capabilities:
                    candidates &= capOfferedBy[cap]
                if candidates:
                    # Build the row.
                    matrix.append([
                        costs[resId] if resId in candidates else infinity
                        for resId in resourceIds
                        ])
                else:
                    # Skip row.
                    if whyNot is not None:
                        whyNot.append(ResourceSpecReason(spec, level))
            if len(matrix) != numRows:
                # Rows were skipped.
                continue

            # Find an assignment.
            assignment = {} # type: Dict[str, Resource]
            for ri, ci in enumerate(cast(List[int], findMatch(matrix))):
                spec = specs[ri]
                resId = resourceIds[ci]
                resource = resources[resId]
                if spec.capabilities.issubset(resource.capabilities):
                    assignment[spec.reference] = resource
                else:
                    if whyNot is not None:
                        whyNot.append(ResourceCapsReason(typeName, level))
                    break
            else:
                # Remember assignment as part of the reservation to return.
                if level == StatusLevel.FREE:
                    reservation.update(assignment)

                # We found a match, so we can skip the remaining status levels.
                break

    return reservation if len(reservation) == len(claim) else None

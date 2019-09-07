# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from typing import (
    AbstractSet, DefaultDict, Dict, Generic, Iterable, Iterator, List,
    Optional, Set, Tuple, TypeVar
)

KT = TypeVar('KT')
VT = TypeVar('VT')

def union(seq: Iterable[AbstractSet[VT]]) -> Set[VT]:
    '''Calculate the union of multiple sets.
    '''
    ret: Set[VT] = set()
    for elem in seq:
        ret |= elem
    return ret

def intersection(seq: Iterable[AbstractSet[VT]]) -> Optional[Set[VT]]:
    '''Calculate the intersection of multiple sets.
    Returns None if the sequence is empty
      (intersection is undefined in that case).
    '''
    ret = None
    for elem in seq:
        if ret is None:
            ret = set(elem)
        else:
            ret &= elem
    return ret

def categorizedLists(
        pairs: Iterable[Tuple[KT, VT]]
        ) -> DefaultDict[KT, List[VT]]:
    '''When given a series of (category, value) pairs, returns a defaultdict
    that has the given categories as the keys and lists containing the
    corresponding values in the same order as in the input.
    The returned defaultdict returns a new empty list if a non-existing key
    is looked up.
    '''
    valuesByCategory: DefaultDict[KT, List[VT]] = defaultdict(list)
    for category, value in pairs:
        valuesByCategory[category].append(value)
    return valuesByCategory

def categorizedSets(
        pairs: Iterable[Tuple[KT, VT]]
        ) -> DefaultDict[KT, Set[VT]]:
    '''When given a series of (category, value) pairs, returns a defaultdict
    that has the given categories as the keys and sets containing the
    corresponding values.
    The returned defaultdict returns a new empty set if a non-existing key
    is looked up.
    '''
    valuesByCategory: DefaultDict[KT, Set[VT]] = defaultdict(set)
    for category, value in pairs:
        valuesByCategory[category].add(value)
    return valuesByCategory

class UnionFind(Generic[VT]):
    '''Keeps track of a number of disjoint sets.
    The sets can be combined (union) and the set containing an element can be
    looked up (find).
    Elements must be usable as dictionary keys.
    '''
    # Implementation notes:
    # Union-find with path compression. Very efficient for large sets.
    # For details:
    #   http://en.wikipedia.org/wiki/Disjoint_set_data_structure
    # I do not see the point of implementing "union by rank" since it requires
    # additional administration and the savings are small if path compression
    # is done.

    def __init__(self) -> None:
        self.__representants: Dict[VT, VT] = {}

    def add(self, elem: VT) -> None:
        '''Adds the given element.
        If it is a new element, it is put in a set by itself.
        If it is an existing element, nothing changes.
        '''
        representants = self.__representants
        if elem not in representants:
            representants[elem] = elem

    def getRepresentant(self, elem: VT) -> VT:
        '''Returns the representant element of the set the given element
        belongs to.
        '''
        representants = self.__representants

        # Find representant.
        currRep = elem
        while True:
            nextRep = representants[currRep]
            if nextRep == currRep:
                break
            currRep = nextRep
        rep = currRep

        # Compress path.
        currRep = elem
        while True:
            nextRep = representants[currRep]
            if nextRep == currRep:
                break
            representants[currRep] = rep
            currRep = nextRep

        return rep

    def unite(self, elem1: VT, elem2: VT) -> None:
        '''Joins the set containing elem1 with the set containing elem2.
        It is allowed for elem1 and elem2 to already belong to the same set.
        '''
        rep1 = self.getRepresentant(elem1)
        rep2 = self.getRepresentant(elem2)
        self.__representants[rep2] = rep1

    def iterSets(self) -> Iterator[Set[VT]]:
        '''Iterates through the disjoint sets kept by this UnionFind.
        The set objects can be freely modified by the caller.
        '''
        return iter(categorizedSets(
            ( self.getRepresentant(member), member )
            for member in self.__representants
            ).values())

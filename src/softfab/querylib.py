# SPDX-License-Identifier: BSD-3-Clause

from operator import itemgetter
from typing import (
    AbstractSet, Callable, Collection, Generic, Iterable, Iterator, List,
    Optional, Type, TypeVar, Union, cast, overload
)

from softfab.compat import Protocol
from softfab.databaselib import DBRecord, Database, Retriever
from softfab.utils import ComparableT, Missing, missing, wildcardMatcher, Comparable


class KeyValueStoreProto(Protocol):
    def __getitem__(self, key: str) -> object:
        ...

Record = TypeVar('Record', bound=KeyValueStoreProto)

class RecordFilter(Generic[Record]):
    '''When called, returns a subset of the records, in the same order as
    they were given.
    '''

    def __call__(self, records: Iterable[Record]) -> Iterable[Record]:
        raise NotImplementedError

class CustomFilter(RecordFilter[Record]):

    def __init__(self, func: Callable[[Record], bool]):
        super().__init__()
        self.__func = func

    def __call__(self, records: Iterable[Record]) -> Iterable[Record]:
        return filter(self.__func, records)

class ValueFilter(RecordFilter[Record], Generic[Record, ComparableT]):
    '''Filter that passes only those records that have the given value for
    the given key.
    '''

    @overload
    def __init__(self, key: str, value: ComparableT, db: None = None):
        ...

    @overload
    def __init__(self: 'ValueFilter[DBRecord, ComparableT]',
                 key: str, value: ComparableT, db: Database[DBRecord]):
        ...

    def __init__(self: 'ValueFilter',
                 key: str,
                 value: ComparableT,
                 db: Optional[Database] = None
                 ):
        super().__init__()
        self.__retriever: Retriever[Record, ComparableT] = _getRetriever(db, key)
        self.__value = value

    def __call__(self, records: Iterable[Record]) -> Iterable[Record]:
        retriever = self.__retriever
        value = self.__value
        for record in records:
            if retriever(record) == value:
                yield record

class WildcardFilter(RecordFilter[Record]):
    '''Filter that passes only those records where the value for the given key
    matches the given wildcard expression.
    '''

    @overload
    def __init__(self, key: str, pattern: str, db: None = None):
        ...

    @overload
    def __init__(self: 'WildcardFilter[DBRecord]',
                 key: str, pattern: str, db: Database[DBRecord]):
        ...

    def __init__(self: 'WildcardFilter',
                 key: str,
                 pattern: str,
                 db: Optional[Database] = None
                 ):
        super().__init__()
        # Note: The caller should only pass keys that have string values,
        #       but the type system cannot enforce that.
        self.__retriever = cast(Retriever[Record, str], _getRetriever(db, key))
        self.__matcher = wildcardMatcher(pattern)

    def __call__(self, records: Iterable[Record]) -> Iterable[Record]:
        retriever = self.__retriever
        matcher = self.__matcher
        for record in records:
            if matcher.match(retriever(record)) is not None:
                yield record

class _BlockFilter(RecordFilter[Record]):
    '''Filter that does not pass any record given to it.
    Used for optimizing special cases in other filters.
    '''

    def __call__(self, records: Iterable[Record]) -> Iterable[Record]:
        return iter(())

class _PassFilter(RecordFilter[Record]):
    '''Filter that passes every record given to it.
    Used for optimizing special cases in other filters.
    '''

    def __call__(self, records: Iterable[Record]) -> Iterable[Record]:
        return iter(records)

class SetFilter(RecordFilter[Record], Generic[Record, ComparableT]):

    @overload
    @classmethod
    def create(cls,
               key: str,
               selected: AbstractSet[ComparableT],
               choices: AbstractSet[ComparableT],
               db: None = None
               ) -> RecordFilter[Record]:
        ...

    @overload
    @classmethod
    def create(cls: Type['SetFilter[DBRecord, ComparableT]'],
               key: str,
               selected: AbstractSet[ComparableT],
               choices: AbstractSet[ComparableT],
               db: Database[DBRecord]
               ) -> RecordFilter[DBRecord]:
        ...

    @classmethod
    def create(cls: Type['SetFilter'],
               key: str,
               selected: AbstractSet[ComparableT],
               choices: AbstractSet[ComparableT],
               db: Optional[Database] = None
               ) -> RecordFilter:
        '''Creates a set filter.
        Use this method instead of the constructor to to have a sanity check
        performed on the arguments and get optimized filters for special cases.
        '''
        assert selected <= choices, sorted(selected - choices)
        numSelected = len(selected)
        numChoices = len(choices)
        if numSelected == 0:
            return _BlockFilter()
        elif numSelected == 1:
            return ValueFilter(key, next(iter(selected)), db)
        elif numSelected == numChoices:
            return _PassFilter()
        else:
            return cls(key, selected, db)

    def __init__(self,
                 key: str,
                 selected: AbstractSet[ComparableT],
                 db: Optional[Database[DBRecord]]
                 ):
        super().__init__()
        # Note: The caller should only pass keys for which the value type
        #       matches 'selected', but the type system cannot enforce that.
        self.__retriever = cast(Retriever[Record, ComparableT],
                                _getRetriever(db, key))
        self.__selected = selected

    def __call__(self, records: Iterable[Record]) -> Iterable[Record]:
        retriever = self.__retriever
        selected = self.__selected
        for record in records:
            if retriever(record) in selected:
                yield record

class RecordSorter(Generic[Record]):
    '''When called, returns the same set of records, in a new order that is
    not dependent on the order in which they were given.
    '''

    def __call__(self, records: Iterable[Record]) -> List[Record]:
        raise NotImplementedError

# TODO: This is the quickest way to solve the problem that None is no
#       longer comparable, but probably not the most efficient. Check
#       whether putting support for 'missing' deeper into the call stack
#       would make an extra step like this unnecessary.
def substMissingForNone(
        retriever: Retriever[Record, Optional[ComparableT]]
        ) -> Retriever[Record, Union[ComparableT, Missing]]:
    def wrap(record: Record,
             retriever: Retriever[Record, Optional[ComparableT]] = retriever
             ) -> Union[ComparableT, Missing]:
        value = retriever(record)
        return missing if value is None else value
    return wrap

def _iterRetrievers(keyOrder: Iterable[str],
                    getRetriever: Callable[[str],
                                           Retriever[Record, Comparable]],
                    uniqueKeys: Collection[str]
                    ) -> Iterator[Retriever[Record, Comparable]]:
    for key in keyOrder:
        yield substMissingForNone(getRetriever(key))
        if key in uniqueKeys:
            # There is no point in another key after a unique key,
            # since the values will never be equal.
            break
    else:
        # As a last resort, use the default sort order of records.
        yield cast(Callable[[Record], Comparable], lambda record: record)

class KeySorter(RecordSorter[Record]):
    '''When called, returns a sorted list of the given database records.
    The keyOrder is a list of the keys by which the records should be sorted,
    in decreasing order of importance.
    For example, [ 'city', 'name' ] would sort the records by city and within
    the same city, by name.
    A function can be passed as a key, in which case it will be called to
    provide a comparison key, just like the 'key' argument to Python's
    built-in sort functions.
    The uniqueKeys argument is a collection of keys (names or functions)
    for which the value is unique for each record. There will be no sorting
    performed on sort criteria behind a unique key in the sort order.
    If two records are equal with respect to the keys in keyOrder,
    their order is determined by comparing the record objects. If the
    record type does not support comparison, you have to provide
    a unique key in the sort order to prevent sorting by record.
    If the database is provided, knowledge about its keys can be used for
    optimizations.
    '''

    @classmethod
    def forCustom(cls: Type['KeySorter[Record]'],
                  keyOrder: Iterable[str],
                  uniqueKeys: Optional[Collection[str]] = None
                  ) -> 'KeySorter[Record]':
        return KeySorter(_iterRetrievers(
            keyOrder, itemgetter, uniqueKeys or ()
            ))

    @classmethod
    def forDB(cls: Type['KeySorter[DBRecord]'],
              keyOrder: Iterable[str],
              db: Database[DBRecord]
              ) -> 'KeySorter[DBRecord]':
        return KeySorter(_iterRetrievers(
            keyOrder, db.retrieverFor, db.uniqueKeys
            ))

    def __init__(self, retrievers: Iterable[Retriever[Record, Comparable]]):
        super().__init__()
        self.__retrievers = tuple(retrievers)

    def __call__(self, records: Iterable[Record]) -> List[Record]:
        # Radix sort: start with least important key and end with most
        # important key; Python's sort guarantees stability of equal elements.
        sortList: Optional[List[Record]] = None
        for retriever in reversed(self.__retrievers):
            if sortList is None:
                sortList = sorted(records, key=retriever)
            else:
                sortList.sort(key=retriever)
        assert sortList is not None
        return sortList

def _getRetriever(db: Optional[Database[DBRecord]],
                  key: str
                  ) -> Retriever[DBRecord, Comparable]:
    '''Returns a function that will retrieve the given key from a record that
    belongs to the given database.
    It is allowed for "db" to be None.
    If an optimized retriever function is available for the given database and
    key (see Database.keyRetrievers), it will be used, otherwise it will fall
    back to a generic retriever.
    '''
    return itemgetter(key) if db is None else db.retrieverFor(key)

RecordProcessor = Callable[[Iterable[Record]], Iterable[Record]]

def runQuery(
        processors: Iterable[RecordProcessor],
        db: Iterable[Record]
        ) -> List[Record]:
    records = db
    for processor in processors:
        records = processor(records)
    return records if isinstance(records, list) else list(records)

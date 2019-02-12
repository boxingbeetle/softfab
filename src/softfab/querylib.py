# SPDX-License-Identifier: BSD-3-Clause

from softfab.utils import missing, wildcardMatcher

from operator import itemgetter

class RecordFilter:
    '''When called, returns a subset of the records, in the same order as
    they were given.
    '''

    def __call__(self, records):
        raise NotImplementedError

class CustomFilter(RecordFilter):

    def __init__(self, func):
        RecordFilter.__init__(self)
        self.__func = func

    def __call__(self, records):
        return filter(self.__func, records)

class ValueFilter(RecordFilter):
    '''Filter that passes only those records that have the given value for
    the given key.
    '''

    def __init__(self, key, value, db = None):
        RecordFilter.__init__(self)
        self.__retriever = _getRetriever(db, key)
        self.__value = value

    def __call__(self, records):
        retriever = self.__retriever
        value = self.__value
        for record in records:
            if retriever(record) == value:
                yield record

class WildcardFilter(RecordFilter):
    '''Filter that passes only those records where the value for the given key
    matches the given wildcard expression.
    '''

    def __init__(self, key, pattern, db = None):
        RecordFilter.__init__(self)
        self.__retriever = _getRetriever(db, key)
        self.__matcher = wildcardMatcher(pattern)

    def __call__(self, records):
        retriever = self.__retriever
        matcher = self.__matcher
        for record in records:
            if matcher.match(retriever(record)) is not None:
                yield record

class _BlockFilter(RecordFilter):
    '''Filter that does not pass any record given to it.
    Used for optimizing special cases in other filters.
    '''

    def __call__(self, records):
        return ()

class _PassFilter(RecordFilter):
    '''Filter that passes every record given to it.
    Used for optimizing special cases in other filters.
    '''

    def __call__(self, records):
        return records

class SetFilter(RecordFilter):

    @classmethod
    def create(cls, key, selected, choices, db = None):
        '''Creates a set filter.
        Use this method instead of the constructor to to have a sanity check
        performed on the arguments and get optimized filters for special cases.
        '''
        assert selected.issubset(choices), ', '.join(
            '%s' % invalid for invalid in sorted(selected.difference(choices))
            )
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

    def __init__(self, key, selected, db):
        RecordFilter.__init__(self)
        self.__retriever = _getRetriever(db, key)
        self.__selected = selected

    def __call__(self, records):
        retriever = self.__retriever
        selected = self.__selected
        for record in records:
            if retriever(record) in selected:
                yield record

class RecordSorter:
    '''When called, returns the same set of records, in a new order that is
    not dependent on the order in which they were given.
    '''

    def __call__(self, records):
        raise NotImplementedError

# TODO: This is the quickest way to solve the problem that None is no
#       longer comparable, but probably not the most efficient. Check
#       whether putting support for 'missing' deeper into the call stack
#       would make an extra step like this unnecessary.
def _substMissingForNone(retriever):
    def wrap(record, retriever=retriever):
        value = retriever(record)
        return missing if value is None else value
    return wrap

class KeySorter(RecordSorter):
    '''When called, returns sorted a list of the given database records.
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

    def __init__(self, keyOrder, db = None, uniqueKeys = None):
        if uniqueKeys is None and db is not None:
            uniqueKeys = db.uniqueKeys

        RecordSorter.__init__(self)
        self.__retrievers = retrievers = []
        for key in keyOrder:
            retrievers.append(_substMissingForNone(
                key if callable(key) else _getRetriever(db, key)
                ))
            if uniqueKeys is not None and key in uniqueKeys:
                # There is no point in another key after a unique key,
                # since the values will never be equal.
                break
        else:
            # As a last resort, use the default sort order of records.
            retrievers.append(lambda record: record)

    def __call__(self, records):
        # Radix sort: start with least important key and end with most
        # important key; Python's sort guarantees stability of equal elements.
        sortList = None
        for retriever in reversed(self.__retrievers):
            if sortList is None:
                sortList = sorted(records, key = retriever)
            else:
                sortList.sort(key = retriever)
        return sortList

def _getRetriever(db, key):
    '''Returns a function that will retrieve the given key from a record that
    belongs to the given database.
    It is allowed for "db" or "key" to be None.
    If an optimized retriever function is available for the given database and
    key (see Database.keyRetrievers), it will be used, otherwise it will fall
    back to a generic retriever.
    '''
    return itemgetter(key) if db is None else db.retrieverFor(key)

def runQuery(processors, db):
    records = db
    for processor in processors:
        records = processor(records)
    return records if isinstance(records, list) else list(records)

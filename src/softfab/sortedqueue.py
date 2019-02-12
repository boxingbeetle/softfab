# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from typing import ClassVar

from softfab.databaselib import RecordObserver, RecordSubjectMixin
from softfab.utils import abstract

def binarySearch(lst, elem, key):
    high = len(lst)
    if high == 0:
        return False, 0
    low = 0
    elemKey = key(elem)
    # inv: if elem in lst then elem in lst[low..high)
    while high - low > 1:
        mid = (low + high) // 2
        if elemKey < key(lst[mid]):
            high = mid
        else:
            low = mid
    lowKey = key(lst[low])
    if elemKey == lowKey:
        return True, low
    elif elemKey < lowKey:
        return False, low
    else: # elemKey > lowKey
        return False, high

class SortedQueue(RecordSubjectMixin, RecordObserver, ABC):
    '''Base class for sorted subsets of databases.
    '''
    compareField = abstract # type: ClassVar[str]

    def __init__(self, db):
        RecordSubjectMixin.__init__(self)
        RecordObserver.__init__(self)
        self.__db = db
        self.__keyFunc = keyFunc = self._getKeyFunc()

        # Compute initial record set.
        filterFunc = self._filter
        self._records = sorted(
            (record for record in db if filterFunc(record)),
            key=keyFunc
            )

        db.addObserver(self)

    def retire(self):
        '''Disconnects this sorted queue from the database it observes,
        so it can be garbage collected.
        '''
        self.__db.removeObserver(self)

    def __iter__(self):
        return iter(self._records)

    def __getitem__(self, index):
        return self._records[index]

    def __len__(self):
        return len(self._records)

    def _filter(self, record): # pylint: disable=unused-argument
        '''By default every record is part of the queue.
        If you only want a subset, override this method to return True iff
        the record should be part of the queue.
        '''
        return True

    def _getKeyFunc(self):
        '''Returns a key function that, when passed a record in this queue,
        returns the sort key for that record.
        The primary ordering is done using the "compareField" class-scope
        field, falling back to comparing by ID if the result is equal.
        If needed, you can override this method to provide a different kind
        of sorting.
        Important: When a record changes its state, its sort key must not
                   change. In practice this means you should only sort on
                   immutable properties of a record.
        '''
        db = self.__db
        compareField = self.compareField
        retriever = db.retrieverFor(compareField)
        if compareField in db.uniqueKeys:
            return retriever
        else:
            return lambda record, retriever=retriever: (
                retriever(record), record.getId()
                )

    def added(self, record):
        if self._filter(record):
            found, index = binarySearch(self._records, record, self.__keyFunc)
            assert not found
            self._records.insert(index, record)
            self._notifyAdded(record)

    def removed(self, record):
        found, index = binarySearch(self._records, record, self.__keyFunc)
        if found:
            del self._records[index]
            self._notifyRemoved(record)

    def updated(self, record):
        found, index = binarySearch(self._records, record, self.__keyFunc)
        if found == self._filter(record):
            if found:
                self._notifyUpdated(record)
        else:
            if found:
                del self._records[index]
                self._notifyRemoved(record)
            else:
                self._records.insert(index, record)
                self._notifyAdded(record)

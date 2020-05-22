# SPDX-License-Identifier: BSD-3-Clause

from pytest import fixture

from softfab.databaselib import Database, DatabaseElem
from softfab.sortedqueue import SortedQueue
from softfab.xmlgen import xml


class Record(DatabaseElem):
    "Minimal implementation of DatabaseElem."
    def __init__(self, properties):
        DatabaseElem.__init__(self)
        self.properties = dict(properties)
        self.retired = False
    def __repr__(self):
        return 'Record(%s)' % self.properties
    def __getitem__(self, key):
        return self.properties[key]
    def __setitem__(self, key, value):
        self.properties[key] = value
        self._notify()
    def getId(self):
        return self.properties['id']
    def toXML(self):
        return xml.record(**self.properties)
    def _retired(self):
        assert not self.retired
        self.retired = True

class RecordFactory:
    "Factory for Record class."
    def createRecord(self, attributes):
        return Record(attributes)

class DB(Database):
    description = 'test'
    privilegeObject = 'x' # dummy

    def __init__(self, baseDir):
        super().__init__(baseDir, RecordFactory())
        self.seqID = 0

    def addRecord(self, value):
        record = Record({
            'id': '%08d' % self.seqID,
            'value': value,
            'flag': True
            })
        self.add(record)
        self.seqID += 1
        return record

@fixture
def db(tmp_path):
    db = DB(str(tmp_path))
    db.preload()
    return db

class Observer:
    "Counts observer notifications from DB."
    def __init__(self):
        self.addedRecords = []
        self.removedRecords = []
        self.updatedRecords = []
    def added(self, record):
        self.addedRecords.append(record)
    def removed(self, record):
        self.removedRecords.append(record)
    def updated(self, record):
        self.updatedRecords.append(record)

class EvenQueue(SortedQueue):
    "Keeps even-valued records, sorted by their value."

    compareField = 'value'

    def _filter(self, record):
        return (record['value'] % 2 == 0) == record['flag']

    @property
    def observer(self):
        observer, = self._observers
        return observer

    def checkRecords(self):
        prevKey = None
        for record in self:
            value = record['value']
            assert self._filter(record)
            key = value, record.getId()
            if prevKey is not None:
                assert prevKey < key
            prevKey = key

    def checkAddOnly(self):
        observer = self.observer
        assert set(observer.addedRecords) == set(self)
        assert observer.removedRecords == []
        assert observer.updatedRecords == []

@fixture
def queue(db):
    observer = Observer()
    queue = EvenQueue(db)
    queue.addObserver(observer)
    return queue

def testZeroToHundred(db, queue):
    "Check values counting from 0 to 100."
    for value in range(101):
        db.addRecord(value)
    assert [record['value'] for record in queue] == list(range(0, 101, 2))
    queue.checkRecords()
    queue.checkAddOnly()

def testHundredToZero(db, queue):
    "Check values counting from 100 to 0."
    for value in range(100, -1, -1):
        db.addRecord(value)
    assert [record['value'] for record in queue] == list(range(0, 101, 2))
    queue.checkRecords()
    queue.checkAddOnly()

def testZeroToHundredShuffle(db, queue):
    "Check values from 0 to 100, inserted in pseudo-random order."
    for value in range(101):
        db.addRecord((value * 13) % 101)
    assert [record['value'] for record in queue] == list(range(0, 101, 2))
    queue.checkRecords()
    queue.checkAddOnly()

def testDuplicates(db, queue):
    "Check values from 0 to 9, inserted multiple times."
    for value in range(100):
        db.addRecord(value % 10)
    assert [record['value'] for record in queue] == [
        x for x in range(10) for y in range(10) if x % 2 == 0
        ]
    queue.checkRecords()
    queue.checkAddOnly()

def testDelete(db, queue):
    "Check deletion of some of the added values."
    added = []
    for value in range(101):
        value = (value * 13) % 101
        record = db.addRecord(value)
        if value % 2 == 0:
            added.append(record)
    removed = []
    for record in list(db.values()):
        value = record['value']
        if value % 3 != 0:
            db.remove(record)
            if value % 2 == 0:
                removed.append(record)
    assert [record['value'] for record in queue] == list(range(0, 101, 6))
    queue.checkRecords()
    observer = queue.observer
    assert observer.addedRecords == added
    assert observer.removedRecords == removed
    assert observer.updatedRecords == []

def testUpdate(db, queue):
    "Check records that are updated."
    added = []
    for value in range(101):
        value = (value * 13) % 101
        record = db.addRecord(value)
        if value % 2 == 0:
            added.append(record)
    updated = []
    for record in list(db.values()):
        value = record['value']
        if value % 3 == 0:
            record['dummy'] = 'no effect'
            if value % 2 == 0:
                updated.append(record)
    queue.checkRecords()
    observer = queue.observer
    assert observer.addedRecords == added
    assert observer.removedRecords == []
    assert observer.updatedRecords == updated

def testUpdateFilter(db, queue):
    "Check records that are filtered in/out when they update."
    added = []
    for value in range(101):
        value = (value * 13) % 101
        record = db.addRecord(value)
        if value % 2 == 0:
            added.append(record)
    removed = []
    for record in list(db.values()):
        value = record['value']
        if value % 3 == 0:
            record['flag'] = False
            if value % 2 == 0:
                removed.append(record)
            else:
                added.append(record)
    queue.checkRecords()
    observer = queue.observer
    assert observer.addedRecords == added
    assert observer.removedRecords == removed
    assert observer.updatedRecords == []

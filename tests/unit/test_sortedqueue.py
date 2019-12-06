# SPDX-License-Identifier: BSD-3-Clause

from softfab.databaselib import Database, DatabaseElem
from softfab.sortedqueue import SortedQueue
from softfab.xmlgen import xml
import os, os.path, unittest

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
    baseDir = 'testdb'
    factory = RecordFactory()
    privilegeObject = 'x' # dummy

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

class TestSortedQueue(unittest.TestCase):

    def setUp(self):
        assert not os.path.exists(DB.baseDir)
        self.db = db = DB()
        db.preload()
        self.observer = observer = Observer()
        self.queue = queue = EvenQueue(db)
        queue.addObserver(observer)
        self.seqID = 0

    def tearDown(self):
        del self.db
        del self.observer
        prefix = DB.baseDir + '/'
        for name in os.listdir(DB.baseDir):
            os.remove(prefix + name)
        os.rmdir(DB.baseDir)

    def addRecord(self, value):
        record = Record({
            'id': '%08d' % self.seqID,
            'value': value,
            'flag': True
            })
        self.db.add(record)
        self.seqID += 1
        return record

    def checkRecords(self):
        prevKey = None
        for record in self.queue:
            value = record['value']
            self.assertTrue(self.queue._filter(record))
            key = value, record.getId()
            if prevKey is not None:
                self.assertLess(prevKey, key)
            prevKey = key

    def checkAddOnly(self):
        self.assertSetEqual(set(self.observer.addedRecords), set(self.queue))
        self.assertListEqual(self.observer.removedRecords, [])
        self.assertListEqual(self.observer.updatedRecords, [])

    def test0100ZeroToHundred(self):
        "Check values counting from 0 to 100."
        for value in range(101):
            self.addRecord(value)
        self.assertListEqual(
            [record['value'] for record in self.queue],
            list(range(0, 101, 2))
            )
        self.checkRecords()
        self.checkAddOnly()

    def test0110HundredToZero(self):
        "Check values counting from 100 to 0."
        for value in range(100, -1, -1):
            self.addRecord(value)
        self.assertListEqual(
            [record['value'] for record in self.queue],
            list(range(0, 101, 2))
            )
        self.checkRecords()
        self.checkAddOnly()

    def test0120ZeroToHundred(self):
        "Check values from 0 to 100, inserted in pseudo-random order."
        for value in range(101):
            self.addRecord((value * 13) % 101)
        self.assertListEqual(
            [record['value'] for record in self.queue],
            list(range(0, 101, 2))
            )
        self.checkRecords()
        self.checkAddOnly()

    def test0130Duplicates(self):
        "Check values from 0 to 9, inserted multiple times."
        for value in range(100):
            self.addRecord(value % 10)
        self.assertListEqual(
            [record['value'] for record in self.queue],
            [x for x in range(10) for y in range(10) if x % 2 == 0]
            )
        self.checkRecords()
        self.checkAddOnly()

    def test0200Delete(self):
        "Check deletion of some of the added values."
        added = []
        for value in range(101):
            value = (value * 13) % 101
            record = self.addRecord(value)
            if value % 2 == 0:
                added.append(record)
        removed = []
        for record in list(self.db.values()):
            value = record['value']
            if value % 3 != 0:
                self.db.remove(record)
                if value % 2 == 0:
                    removed.append(record)
        self.assertListEqual(
            [record['value'] for record in self.queue],
            list(range(0, 101, 6))
            )
        self.checkRecords()
        self.assertListEqual(self.observer.addedRecords, added)
        self.assertListEqual(self.observer.removedRecords, removed)
        self.assertListEqual(self.observer.updatedRecords, [])

    def test0300Update(self):
        "Check records that are updated."
        added = []
        for value in range(101):
            value = (value * 13) % 101
            record = self.addRecord(value)
            if value % 2 == 0:
                added.append(record)
        updated = []
        for record in list(self.db.values()):
            value = record['value']
            if value % 3 == 0:
                record['dummy'] = 'no effect'
                if value % 2 == 0:
                    updated.append(record)
        self.checkRecords()
        self.assertListEqual(self.observer.addedRecords, added)
        self.assertListEqual(self.observer.removedRecords, [])
        self.assertListEqual(self.observer.updatedRecords, updated)

    def test0310UpdateFilter(self):
        "Check records that are filtered in/out when they update."
        added = []
        for value in range(101):
            value = (value * 13) % 101
            record = self.addRecord(value)
            if value % 2 == 0:
                added.append(record)
        removed = []
        for record in list(self.db.values()):
            value = record['value']
            if value % 3 == 0:
                record['flag'] = False
                if value % 2 == 0:
                    removed.append(record)
                else:
                    added.append(record)
        self.checkRecords()
        self.assertListEqual(self.observer.addedRecords, added)
        self.assertListEqual(self.observer.removedRecords, removed)
        self.assertListEqual(self.observer.updatedRecords, [])

if __name__ == '__main__':
    unittest.main()

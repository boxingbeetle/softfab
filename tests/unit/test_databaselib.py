# SPDX-License-Identifier: BSD-3-Clause

import os, os.path, random, time, unittest

from softfab import databaselib
from softfab.xmlgen import xml

class Record(databaselib.DatabaseElem):
    "Minimal implementation of DatabaseElem."
    def __init__(self, properties):
        databaselib.DatabaseElem.__init__(self)
        self.properties = dict(properties)
        self.retired = False
    def getId(self):
        return self.properties['id']
    def toXML(self):
        return xml.record(**self.properties)
    def _retired(self):
        assert not self.retired
        self.retired = True

class IntentionalError(Exception):
    "Thrown to test handling of arbitrary errors."
    pass

class FaultyRecord(Record):
    def toXML(self):
        raise IntentionalError('broken on purpose')

class RecordFactory:
    "Factory for Record class."
    def createRecord(self, attributes):
        return Record(attributes)

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

class BasicTests:
    """Test basic Database functionality.
    Contains reusable implementation for TestDatabase and
    TestVersionedDatabase, but should not be run in itself,
    therefore does not extend TestCase.

    Every test case checks both the in-memory database (same db object on which
    operations were performed) and the on-disk database (call to createDB()
    after operations were performed).
    """

    def __init__(self):
        pass

    def setUp(self):
        self.dbDir = 'testdb'
        self.record = Record( { 'id': 'id_abc', 'a': '1', 'b': '2' } )
        self.faultyRecord = FaultyRecord(
            { 'id': 'id_abc', 'a': '1', 'b': '2' }
            )
        self.putRecord1 = Record( { 'id': self.record.getId(), 'ver': 'old' } )
        self.putRecord2 = self.record
        assert not os.path.exists(self.dbDir)

    def tearDown(self):
        prefix = self.dbDir + '/'
        for file in os.listdir(self.dbDir):
            os.remove(prefix + file)
        os.rmdir(self.dbDir)

    def createDB(self, recordFactory=RecordFactory(), keyChecker=None):
        class DB(self.dbClass):
            baseDir = self.dbDir
            factory = recordFactory
            description = 'test'
            alwaysInMemory = False
            privilegeObject = 'x' # dummy
            if keyChecker is not None:
                def _customCheckId(self, key):
                    keyChecker(key)
        db = DB()
        observer = Observer()
        db.addObserver(observer)
        return db, observer

    def checkEmpty(self, db):
        "Check that given database has no records."
        self.assertTrue(len(db) == 0, len(db))
        self.assertRaises(KeyError, lambda: db[self.record.getId()])
        self.assertEqual(db.get(self.record.getId()), None)
        self.assertEqual(len(list(db.keys())), 0)
        self.assertEqual(len(list(db.values())), 0)
        self.assertEqual(len(list(db.items())), 0)
        self.assertEqual([ record for record in db ], [])
        self.assertRaises(KeyError, lambda: db.remove(self.record))

    def checkOne(self, db):
        "Check that given database has one record."
        self.assertTrue(len(db) == 1, len(db))
        self.assertEqual(db[self.record.getId()], self.record)
        self.assertEqual(db.get(self.record.getId()), self.record)
        self.assertEqual(
            db[self.record.getId()].properties,
            self.record.properties
            )
        self.assertEqual(
            db.get(self.record.getId()).properties,
            self.record.properties
            )
        self.assertEqual(list(db.keys()), [ self.record.getId() ])
        self.assertEqual(list(db.values()), [ self.record ])
        self.assertEqual(
            list(db.items()), [ (self.record.getId(), self.record) ]
            )
        self.assertEqual([ record for record in db ], [ self.record ])
        self.assertRaises(KeyError, lambda: db.add(self.record))

    def checkNotify(self, observer, added = [], removed = [], updated = []):
        self.assertEqual(observer.addedRecords, added)
        self.assertEqual(observer.removedRecords, removed)
        self.assertEqual(observer.updatedRecords, updated)

    def runMixedAction(self, db, rnd):
        keys = []
        dataDict = {}
        removed = set()

        def add():
            while True:
                key = ''.join( [
                    chr(rnd.randrange(ord('a'), ord('z') + 1))
                    for i in range(10)
                    ] )
                if key not in keys and key not in removed:
                    break
            data = rnd.randrange(1 << 30)
            db.add(Record( { 'id': key, 'data': data } ))
            keys.append(key)
            dataDict[key] = data

        def resurrect():
            if len(removed) == 0:
                return
            key = list(removed)[rnd.randrange(len(removed))]
            data = rnd.randrange(1 << 30)
            db.add(Record( { 'id': key, 'data': data } ))
            keys.append(key)
            dataDict[key] = data
            removed.remove(key)

        def remove():
            if len(keys) == 0:
                return add()
            i = rnd.randrange(len(keys))
            key = keys[i]
            record = db[key]
            db.remove(record)
            del keys[i]
            del dataDict[key]
            removed.add(key)

        def update():
            if len(keys) == 0:
                return add()
            i = rnd.randrange(len(keys))
            key = keys[i]
            data = rnd.randrange(1 << 30)
            db.update(Record( { 'id': key, 'data': data } ))
            dataDict[key] = data

        choices = (add,) * 4 + (resurrect,) * 1 + (remove,) * 2 + (update,) * 8
        for i in range(1000):
            rnd.choice(choices)()

        # Check that the test itself is consistent.
        self.assertEqual(sorted(keys), sorted(dataDict.keys()))

        return dataDict

    def runMixedCheck(self, db, dataDict):
        dbDict = {}
        for record in db:
            dbDict[record.getId()] = int(record.properties['data'])
        # Compare keys first, to make problems easier to find.
        self.assertEqual(sorted(dbDict.keys()), sorted(dataDict.keys()))
        # Now compare complete dictionary.
        self.assertEqual(dbDict, dataDict)

    def runMixed(self, seed):
        db, observer = self.createDB()
        dataDict = self.runMixedAction(db, random.Random(seed))
        self.runMixedCheck(db, dataDict)
        db, observer = self.createDB()
        self.runMixedCheck(db, dataDict)

    def test0010Empty(self):
        "Test empty DB."
        db, observer = self.createDB()
        self.checkEmpty(db)
        self.checkNotify(observer)
        db, observer = self.createDB()
        self.checkEmpty(db)

    def test0020Add(self):
        "Test adding of one record."
        db, observer = self.createDB()
        db.add(self.record)
        self.checkOne(db)
        self.checkNotify(observer, added = [ self.record ] )
        db, observer = self.createDB()
        self.checkOne(db)

    def test0021AddFaulty(self):
        "Test handling of faulty record."
        db, observer = self.createDB()
        self.assertRaises(IntentionalError, lambda: db.add(self.faultyRecord))
        self.checkEmpty(db)
        self.checkNotify(observer)
        db, observer = self.createDB()
        self.checkEmpty(db)

    __invalidKeys = [
            '',
            '/abc', '../abc',
            'abc/def', 'abc>def', 'abc!def', 'abc:def',
            'abc|0001',
            r'c:\temp\abc', r'\temp\abc',
            '*.xml',
            'abc\ndef',
            ' abc', 'abc ', 'ab  cd',
            ]

    def test0022AddInvalidKey(self):
        "Test handling of invalid characters in key."
        db, observer = self.createDB()
        for key in self.__invalidKeys:
            record = Record( { 'id': key, 'a': '1', 'b': '2' } )
            self.assertRaises(KeyError, lambda: db.add(record))
        self.checkEmpty(db)
        self.checkNotify(observer)
        db, observer = self.createDB()
        self.checkEmpty(db)

    def test0023AddCustomKeyChecker(self):
        "Test custom key checker handling of valid key."
        def customChecker(key):
            if len(key) != 3:
                raise KeyError('letters in key must be three')
        db, observer = self.createDB(keyChecker = customChecker)
        validKeys = ['abc', '123', 'foo']
        records = []
        for key in validKeys:
            record = Record( { 'id': key, 'a': '1', 'b': '2' } )
            db.add(record)
            records.append(record)
        self.assertEqual(sorted(db.keys()), sorted(validKeys))
        self.checkNotify(observer, added = records)
        db, observer = self.createDB()
        self.assertEqual(sorted(db.keys()), sorted(validKeys))

    def test0024AddCustomKeyCheckerInvalidKey(self):
        "Test custom key checker handling of invalid characters in key."
        def customChecker(key):
            if len(key) != 3:
                raise KeyError('letters in key must be three')
        db, observer = self.createDB(keyChecker = customChecker)
        for key in self.__invalidKeys + [
            'a', 'ab', 'abcd', 'abcde'
            ]:
            record = Record( { 'id': key, 'a': '1', 'b': '2' } )
            self.assertRaises(KeyError, lambda: db.add(record))
        self.checkEmpty(db)
        self.checkNotify(observer)
        db, observer = self.createDB()
        self.checkEmpty(db)

    def test0030Remove(self):
        "Test removal of one record."
        db, observer = self.createDB()
        db.add(self.record)
        db.remove(self.record)
        self.checkEmpty(db)
        self.checkNotify(observer,
            added = [ self.record ], removed = [ self.record ] )
        self.assertTrue(self.record.retired)
        db, observer = self.createDB()
        self.checkEmpty(db)

    def test0040Update(self):
        "Test explicit update of a record."
        db, observer = self.createDB()
        key = self.record.getId()
        db.add(self.putRecord1)
        db.update(self.putRecord2)
        self.checkOne(db)
        self.checkNotify(observer,
            added = [ self.putRecord1 ], updated = [ self.putRecord2 ] )
        self.assertTrue(self.putRecord1.retired)
        self.assertTrue(not self.putRecord2.retired)
        db, observer = self.createDB()
        self.checkOne(db)

    def test0041UpdateInvalid(self):
        "Test explicit update of non-existant record."
        db, observer = self.createDB()
        self.assertRaises(KeyError, lambda: db.update(self.record))
        self.checkEmpty(db)
        self.checkNotify(observer)
        db, observer = self.createDB()
        self.checkEmpty(db)

    def test0050Mixed(self):
        "Test mixed addition, update and removal."
        seed = int(time.time())
        # Printing random seed makes it possible to reproduce a problem
        # if it only occurs for certain seeds.
        # I'm not sure how likely this is, but it's better to have the seed
        # than to find it lost forever in case it does make a difference.
        print('Random seed: %d' % seed)
        self.runMixed(seed)

    def test0051Mixed(self):
        "Test mixed addition, update and removal."
        self.runMixed(0)

    def test0052Mixed(self):
        "Test mixed addition, update and removal."
        self.runMixed(1234567890)

class TestDatabase(BasicTests, unittest.TestCase):
    "Test basic Database functionality."

    dbClass = databaselib.Database

    def __init__(self, methodName = 'runTest'):
        BasicTests.__init__(self)
        unittest.TestCase.__init__(self, methodName)

    def test0060Modify(self):
        "Test auto-saving of modified record."
        db, observer = self.createDB()
        record = Record( { 'id': 'id_mod' } )
        db.add(record)
        record.properties['modified'] = 'true'
        record._notify()
        self.checkNotify(observer, added = [ record ], updated = [ record ] )
        db, observer = self.createDB()
        savedRecord = db['id_mod']
        self.assertEqual(savedRecord.properties.get('modified'), 'true')

class TestVersionedDatabase(BasicTests, unittest.TestCase):
    "Test functionality of VersionedDatabase."

    dbClass = databaselib.VersionedDatabase

    def __init__(self, methodName = 'runTest'):
        BasicTests.__init__(self)
        unittest.TestCase.__init__(self, methodName)

    def checkVersions(self, db, version1, version2):
        self.checkOne(db)
        self.assertNotEqual(version1, version2)
        self.assertEqual(
            db.getVersion(version1).properties, self.putRecord1.properties )
        self.assertEqual(
            db.getVersion(version2).properties, self.putRecord2.properties )

    def test0060Modify(self):
        "Test modification detection of versioned record."
        db, observer = self.createDB()
        record = Record( { 'id': 'id_mod' } )
        db.add(record)
        self.assertRaises(RuntimeError, lambda: record._notify())
        self.checkNotify(observer, added = [ record ])

    # Test versioning:

    def test0100Update(self):
        "Test explicit update of a versioned record."
        db, observer = self.createDB()
        key = self.record.getId()
        db.add(self.putRecord1)
        version1 = db.latestVersion(key)
        db.update(self.putRecord2)
        version2 = db.latestVersion(key)

        self.checkVersions(db, version1, version2)
        self.checkNotify(observer,
            added = [ self.putRecord1 ], updated = [ self.putRecord2 ] )
        self.assertTrue(self.putRecord1.retired)
        self.assertTrue(not self.putRecord2.retired)
        db, observer = self.createDB()
        self.checkVersions(db, version1, version2)

    def test0110Remove(self):
        "Test accessiblity of old version of removed record."
        db, observer = self.createDB()
        db.add(self.record)
        version = db.latestVersion(self.record.getId())
        db.remove(self.record)

        self.assertEqual(
            db.getVersion(version).properties,
            self.record.properties
            )
        self.checkNotify(observer,
            added = [ self.record ], removed = [ self.record ] )
        self.assertTrue(self.record.retired)
        db, observer = self.createDB()
        self.assertEqual(
            db.getVersion(version).properties,
            self.record.properties
            )

    def test0120Resurrect(self):
        "Test add / remove / add."
        db, observer = self.createDB()
        key = self.record.getId()
        db.add(self.putRecord1)
        version1 = db.latestVersion(key)
        db.remove(self.putRecord1)
        db.add(self.putRecord2)
        version2 = db.latestVersion(key)
        self.assertNotEqual(version1, version2)

        self.checkVersions(db, version1, version2)
        self.checkNotify(observer,
            added = [ self.putRecord1, self.putRecord2 ],
            removed = [ self.putRecord1 ]
            )
        self.assertTrue(self.putRecord1.retired)
        self.assertTrue(not self.putRecord2.retired)
        db, observer = self.createDB()
        self.checkVersions(db, version1, version2)

if __name__ == '__main__':
    unittest.main()

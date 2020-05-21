# SPDX-License-Identifier: BSD-3-Clause

"""Test Database and VersionedDatabase functionality.

Every test case checks both the in-memory database (same db object on which
operations were performed) and the on-disk database (call to createDB()
after operations were performed).
"""

from pytest import fixture, mark, raises

import random, time

from softfab.databaselib import Database, DatabaseElem, VersionedDatabase
from softfab.xmlgen import xml


RECORD_ID = 'id_abc'

class Record(DatabaseElem):
    "Minimal implementation of DatabaseElem."
    def __init__(self, properties):
        super().__init__()
        self.properties = dict(properties)
        self.retired = False
    def getId(self):
        return self.properties['id']
    def toXML(self):
        return xml.record(**self.properties)
    def _retired(self):
        assert not self.retired
        self.retired = True

    @classmethod
    def create(cls):
        return cls({'id': RECORD_ID, 'a': '1', 'b': '2'})

    @classmethod
    def createOld(cls):
        return cls({'id': RECORD_ID, 'ver': 'old'})

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

@fixture
def createDB(tmp_path, request):
    dbDir = tmp_path
    dbClass = request.param

    def dbFactory(recordFactory=RecordFactory(), keyChecker=None):
        class DB(dbClass):
            description = 'test'
            privilegeObject = 'x' # dummy
            if keyChecker is not None:
                def _customCheckId(self, key):
                    keyChecker(key)
        db = DB(dbDir, recordFactory)
        db.preload()
        observer = Observer()
        db.addObserver(observer)
        return db, observer

    return dbFactory

def checkEmpty(db):
    "Check that given database has no records."
    assert len(db) == 0
    with raises(KeyError):
        db[RECORD_ID]
    assert db.get(RECORD_ID) == None
    assert len(list(db.keys())) == 0
    assert len(list(db.values())) == 0
    assert len(list(db.items())) == 0
    assert [record for record in db] == []
    with raises(KeyError):
        db.remove(Record.create())

def checkOne(db, record):
    "Check that given database has one record."
    assert len(db) == 1
    assert db[record.getId()] == record
    assert db.get(record.getId()) == record
    assert db[record.getId()].properties == record.properties
    assert db.get(record.getId()).properties == record.properties
    assert list(db.keys()) == [record.getId()]
    assert list(db.values()) == [record]
    assert list(db.items()) == [(record.getId(), record)]
    assert [record for record in db] == [record]
    with raises(KeyError):
        db.add(record)

def checkVersions(db, version1, record1, version2, record2):
    checkOne(db, record2)
    assert version1 != version2
    assert db.getVersion(version1).properties == record1.properties
    assert db.getVersion(version2).properties == record2.properties

def checkNotify(observer, added=[], removed=[], updated=[]):
    assert observer.addedRecords == added
    assert observer.removedRecords == removed
    assert observer.updatedRecords == updated

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testEmpty(createDB):
    "Test empty DB."
    db, observer = createDB()
    checkEmpty(db)
    checkNotify(observer)
    db, observer = createDB()
    checkEmpty(db)

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testAdd(createDB):
    "Test adding of one record."
    db, observer = createDB()
    record = Record.create()
    db.add(record)
    checkOne(db, record)
    checkNotify(observer, added=[record])
    db, observer = createDB()
    checkOne(db, record)

class IntentionalError(Exception):
    "Thrown to test handling of arbitrary errors."

class FaultyRecord(Record):
    def toXML(self):
        raise IntentionalError('broken on purpose')

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testAddFaulty(createDB):
    "Test handling of faulty record."
    db, observer = createDB()
    faultyRecord = FaultyRecord({'id': 'id_abc', 'a': '1', 'b': '2'})
    with raises(IntentionalError):
        db.add(faultyRecord)
    checkEmpty(db)
    checkNotify(observer)
    db, observer = createDB()
    checkEmpty(db)

invalidKeys = [
        '',
        '/abc', '../abc',
        'abc/def', 'abc>def', 'abc!def', 'abc:def',
        'abc|0001',
        r'c:\temp\abc', r'\temp\abc',
        '*.xml',
        'abc\ndef',
        ' abc', 'abc ', 'ab  cd',
        ]

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testAddInvalidKey(createDB):
    "Test handling of invalid characters in key."
    db, observer = createDB()
    for key in invalidKeys:
        record = Record({'id': key, 'a': '1', 'b': '2'})
        with raises(KeyError):
            db.add(record)
    checkEmpty(db)
    checkNotify(observer)
    db, observer = createDB()
    checkEmpty(db)

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testAddCustomKeyChecker(createDB):
    "Test custom key checker handling of valid key."
    def customChecker(key):
        if len(key) != 3:
            raise KeyError('letters in key must be three')
    db, observer = createDB(keyChecker = customChecker)
    validKeys = ['abc', '123', 'foo']
    records = []
    for key in validKeys:
        record = Record({'id': key, 'a': '1', 'b': '2'})
        db.add(record)
        records.append(record)
    assert sorted(db.keys()) == sorted(validKeys)
    checkNotify(observer, added = records)
    db, observer = createDB()
    assert sorted(db.keys()) == sorted(validKeys)

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testAddCustomKeyCheckerInvalidKey(createDB):
    "Test custom key checker handling of invalid characters in key."
    def customChecker(key):
        if len(key) != 3:
            raise KeyError('letters in key must be three')
    db, observer = createDB(keyChecker = customChecker)
    for key in invalidKeys + ['a', 'ab', 'abcd', 'abcde']:
        record = Record({'id': key, 'a': '1', 'b': '2'})
        with raises(KeyError):
            db.add(record)
    checkEmpty(db)
    checkNotify(observer)
    db, observer = createDB()
    checkEmpty(db)

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testRemove(createDB):
    "Test removal of one record."
    db, observer = createDB()
    record = Record.create()
    db.add(record)
    db.remove(record)
    checkEmpty(db)
    checkNotify(observer, added=[record], removed=[record])
    assert record.retired
    db, observer = createDB()
    checkEmpty(db)

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testUpdate(createDB):
    "Test explicit update of a record."
    db, observer = createDB()
    oldRecord = Record.createOld()
    db.add(oldRecord)
    record = Record.create()
    db.update(record)
    checkOne(db, record)
    checkNotify(observer, added=[oldRecord],
                               updated=[record])
    assert oldRecord.retired
    assert not record.retired
    db, observer = createDB()
    checkOne(db, record)

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testUpdateInvalid(createDB):
    "Test explicit update of non-existant record."
    db, observer = createDB()
    record = Record.create()
    with raises(KeyError):
        db.update(record)
    checkEmpty(db)
    checkNotify(observer)
    db, observer = createDB()
    checkEmpty(db)

def runMixedAction(db, rnd):
    keys = []
    dataDict = {}
    removed = set()

    def add():
        while True:
            key = ''.join(
                chr(rnd.randrange(ord('a'), ord('z') + 1))
                for i in range(10)
                )
            if key not in keys and key not in removed:
                break
        data = rnd.randrange(1 << 30)
        db.add(Record({'id': key, 'data': data}))
        keys.append(key)
        dataDict[key] = data

    def resurrect():
        if len(removed) == 0:
            return
        key = list(removed)[rnd.randrange(len(removed))]
        data = rnd.randrange(1 << 30)
        db.add(Record({'id': key, 'data': data}))
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
        db.update(Record({'id': key, 'data': data}))
        dataDict[key] = data

    choices = (add,) * 4 + (resurrect,) * 1 + (remove,) * 2 + (update,) * 8
    for i in range(1000):
        rnd.choice(choices)()

    # Check that the test itself is consistent.
    assert sorted(keys) == sorted(dataDict.keys())

    return dataDict

def runMixedCheck(db, dataDict):
    dbDict = {}
    for record in db:
        dbDict[record.getId()] = int(record.properties['data'])
    # Compare keys first, to make problems easier to find.
    assert sorted(dbDict.keys()) == sorted(dataDict.keys())
    # Now compare complete dictionary.
    assert dbDict == dataDict

def runMixed(seed, createDB):
    db, observer = createDB()
    dataDict = runMixedAction(db, random.Random(seed))
    runMixedCheck(db, dataDict)
    db, observer = createDB()
    runMixedCheck(db, dataDict)

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testMixed0(createDB):
    "Test mixed addition, update and removal."
    runMixed(0, createDB)

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testMixed1234567890(createDB):
    "Test mixed addition, update and removal."
    runMixed(1234567890, createDB)

@mark.parametrize('createDB', [Database, VersionedDatabase], indirect=True)
def testMixedRandom(createDB):
    "Test mixed addition, update and removal."
    seed = int(time.time())
    # Printing random seed makes it possible to reproduce a problem
    # if it only occurs for certain seeds.
    # I'm not sure how likely this is, but it's better to have the seed
    # than to find it lost forever in case it does make a difference.
    print('Random seed: %d' % seed)
    runMixed(seed, createDB)

@mark.parametrize('createDB', [Database], indirect=True)
def testUnversionedModify(createDB):
    "Test auto-saving of modified record."
    db, observer = createDB()
    record = Record({'id': 'id_mod'})
    db.add(record)
    record.properties['modified'] = 'true'
    record._notify()
    checkNotify(observer, added=[record], updated=[record])
    db, observer = createDB()
    savedRecord = db['id_mod']
    assert savedRecord.properties.get('modified') == 'true'

@mark.parametrize('createDB', [VersionedDatabase], indirect=True)
def testVersionedModify(createDB):
    "Test modification detection of versioned record."
    db, observer = createDB()
    record = Record({'id': 'id_mod'})
    db.add(record)
    with raises(RuntimeError):
        record._notify()
    checkNotify(observer, added=[record])

@mark.parametrize('createDB', [VersionedDatabase], indirect=True)
def testVersionedUpdate(createDB):
    "Test explicit update of a versioned record."
    db, observer = createDB()

    oldRecord = Record.createOld()
    db.add(oldRecord)
    key = oldRecord.getId()
    version1 = db.latestVersion(key)

    record = Record.create()
    assert record.getId() == key
    db.update(record)
    version2 = db.latestVersion(key)

    checkVersions(db, version1, oldRecord, version2, record)
    checkNotify(observer, added=[oldRecord], updated=[record])
    assert oldRecord.retired
    assert not record.retired
    db, observer = createDB()
    checkVersions(db, version1, oldRecord, version2, record)

@mark.parametrize('createDB', [VersionedDatabase], indirect=True)
def testVersionedRemove(createDB):
    "Test accessiblity of old version of removed record."
    db, observer = createDB()
    record = Record.create()
    db.add(record)
    version = db.latestVersion(record.getId())
    db.remove(record)

    assert db.getVersion(version).properties == record.properties
    checkNotify(observer, added=[record], removed=[record])
    assert record.retired
    db, observer = createDB()
    assert db.getVersion(version).properties == record.properties

@mark.parametrize('createDB', [VersionedDatabase], indirect=True)
def testResurrect(createDB):
    "Test add / remove / add."
    db, observer = createDB()

    oldRecord = Record.createOld()
    key = oldRecord.getId()
    db.add(oldRecord)
    version1 = db.latestVersion(key)

    db.remove(oldRecord)
    record = Record.create()
    assert record.getId() == key
    db.add(record)
    version2 = db.latestVersion(key)
    assert version1 != version2

    checkVersions(db, version1, oldRecord, version2, record)
    checkNotify(observer, added=[oldRecord, record], removed=[oldRecord])
    assert oldRecord.retired
    assert not record.retired
    db, observer = createDB()
    checkVersions(db, version1, oldRecord, version2, record)

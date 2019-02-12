# SPDX-License-Identifier: BSD-3-Clause

from initconfig import config

from softfab import databases, storagelib
from datageneratorlib import removeRec

import unittest

def convertToAbsoluteURL(url, storageId):
    storage = storagelib._lookupStorage(storageId)
    if storage is None:
        return None
    else:
        return storage.joinURL(url)

class TestStorageLib(object):
    "Test storagelib API."
    storageId1 = 'storage1'
    storageId2 = 'storage2'
    storageId3 = 'storage3'
    storageName1 = 'name1'
    storageName2 = 'name2'
    storageName3 = 'name3'
    storageURL1 = 'http://host1/path1/'
    storageURL2 = 'ftp://host2/path2a/path2b/'
    storageURL3 = 'file:///path3a/path3b/path3c/'

    def reloadDatabases(self):
        databases.reloadDatabases()

    def setUp(self):
        self.reloadDatabases()

    def tearDown(self):
        removeRec(config.dbDir)

    def createStorage(self, id, name, url, aliases = ()):
        storage = storagelib.Storage( {
            'id': id,
            'name': name,
            'url': url,
            } )
        for alias in aliases:
            storage._addAlias({'id': alias})
        return storage

    def addStorage(self, id, name, url, aliases = ()):
        storage = self.createStorage(id, name, url, aliases)
        storagelib.storageDB.add(storage)
        return storage

class Test0100Basic(TestStorageLib, unittest.TestCase):
    '''Test a few basic scenarios for using storagelib.
    '''

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)

    def test0100Mappings(self):
        '''Test name, alias and URL mappings.
        '''
        # Add one storage and check the mappings
        self.addStorage(self.storageId1, self.storageName1, self.storageURL1)

        self.assertEqual(
            list(storagelib.storageDB.keys()),
            [self.storageId1]
            )
        self.assertEqual(
            storagelib._storageNames, {self.storageName1: self.storageId1}
            )
        self.assertEqual(
            storagelib._storageURLMap, {self.storageURL1: self.storageId1}
            )
        self.assertEqual(storagelib._storageAliases, {})

        # Add one more storage and check the mappings again
        self.addStorage(self.storageId2, self.storageName2, self.storageURL2,
            ( 'alias1', 'alias2', 'alias3' )
            )

        self.assertEqual(
            set(storagelib.storageDB.keys()),
            set([self.storageId1, self.storageId2])
            )
        self.assertEqual(
            storagelib._storageNames, {
                self.storageName1: self.storageId1,
                self.storageName2: self.storageId2,
                }
            )
        self.assertEqual(
            storagelib._storageURLMap, {
                self.storageURL1: self.storageId1,
                self.storageURL2: self.storageId2,
                }
            )
        self.assertEqual(storagelib._storageAliases, {
            'alias1': self.storageId2,
            'alias2': self.storageId2,
            'alias3': self.storageId2,
            })

        # Replace one of the storages and check the mappings
        storage = self.createStorage(self.storageId2, self.storageName3,
            self.storageURL3, ('alias1', 'alias3', 'alias4')
            )
        storagelib.storageDB.update(storage)

        self.assertEqual(
            set(storagelib.storageDB.keys()),
            set([self.storageId1, self.storageId2])
            )
        self.assertEqual(
            storagelib._storageNames, {
                self.storageName1: self.storageId1,
                self.storageName3: self.storageId2,
                }
            )
        self.assertEqual(
            storagelib._storageURLMap, {
                self.storageURL1: self.storageId1,
                self.storageURL3: self.storageId2,
                }
            )
        self.assertEqual(storagelib._storageAliases, {
            'alias1': self.storageId2,
            'alias3': self.storageId2,
            'alias4': self.storageId2,
            })

        # Remove one of the storages and check the mappings
        storagelib.storageDB.remove(storagelib.storageDB[self.storageId1])

        self.assertEqual(
            list(storagelib.storageDB.keys()),
            [self.storageId2]
            )
        self.assertEqual(
            storagelib._storageNames, {
                self.storageName3: self.storageId2,
                }
            )
        self.assertEqual(
            storagelib._storageURLMap, {
                self.storageURL3: self.storageId2,
                }
            )
        self.assertEqual(storagelib._storageAliases, {
            'alias1': self.storageId2,
            'alias3': self.storageId2,
            'alias4': self.storageId2,
            })

        # Remove the remaining storage and make sure the mappings are empty
        storagelib.storageDB.remove(storagelib.storageDB[self.storageId2])

        self.assertEqual(len(storagelib.storageDB), 0)
        self.assertEqual(storagelib._storageNames, {})
        self.assertEqual(storagelib._storageURLMap, {})
        self.assertEqual(storagelib._storageAliases, {})

    def test0200ConvertURLs(self):
        '''Test URL conversion with the existing storages.
        '''
        suffix1 = 'jobpath1/taskpath1/'
        suffix2 = 'jobpath1/taskpath2/'
        suffix3 = 'jobpath1/taskpath2/filename'
        suffix4 = 'jobpath2/taskpath3/'
        self.addStorage(self.storageId1, self.storageName1, self.storageURL1)
        self.addStorage(self.storageId2, self.storageName2, self.storageURL2)
        self.addStorage(self.storageId3, self.storageName3, self.storageURL3)
        absURL1 = self.storageURL1 + suffix1
        absURL2 = self.storageURL2 + suffix2
        absURL3 = self.storageURL2 + suffix3
        absURL4 = self.storageURL3 + suffix3
        absURL5 = self.storageURL3 + suffix4
        relURL1, storageId1 = \
            storagelib._convertToRelativeURL(absURL1, 'to_be_ignored')
        relURL2, storageId2 = \
            storagelib._convertToRelativeURL(absURL2, 'to_be_ignored')
        relURL3, storageId3 = \
            storagelib._convertToRelativeURL(absURL3, 'to_be_ignored')
        relURL4, storageId4 = \
            storagelib._convertToRelativeURL(absURL4, 'to_be_ignored')
        relURL5, storageId5 = \
            storagelib._convertToRelativeURL(absURL5)
        # Check if the URL has been split correctly
        self.assertEqual(relURL1, suffix1)
        self.assertEqual(relURL2, suffix2)
        self.assertEqual(relURL3, suffix3)
        self.assertEqual(relURL4, suffix3)
        self.assertEqual(relURL5, suffix4)
        # Check if the correct storage has been found
        self.assertEqual(storageId1, self.storageId1)
        self.assertEqual(storageId2, self.storageId2)
        self.assertEqual(storageId3, self.storageId2)
        self.assertEqual(storageId4, self.storageId3)
        self.assertEqual(storageId5, self.storageId3)
        # Check that the URLs are converted back correctly
        self.assertEqual(
            convertToAbsoluteURL(relURL1, storageId1), absURL1
            )
        self.assertEqual(
            convertToAbsoluteURL(relURL2, storageId2), absURL2
            )
        self.assertEqual(
            convertToAbsoluteURL(relURL3, storageId3), absURL3
            )
        self.assertEqual(
            convertToAbsoluteURL(relURL4, storageId4), absURL4
            )
        self.assertEqual(
            convertToAbsoluteURL(relURL5, storageId5), absURL5
            )
        # Check that no new storages have been added
        self.assertEqual(len(storagelib.storageDB), 3)
        # Check if the storage names remain unchanged
        self.assertEqual(
            storagelib.storageDB[self.storageId1]['name'], self.storageName1
            )
        self.assertEqual(
            storagelib.storageDB[self.storageId2]['name'], self.storageName2
            )
        self.assertEqual(
            storagelib.storageDB[self.storageId3]['name'], self.storageName3
            )

    def test0300AutoCreate(self):
        '''Test automatic storage creation when a new URL comes in.
        '''
        # Make sure a new storage is created for a new URL
        suffix1 = 'jobpath1/taskpath1/'
        suffix2 = 'jobpath1/taskpath2/'
        suffix3 = 'jobpath1/taskpath2/filename'
        absURL1 = self.storageURL1 + suffix1
        absURL2 = self.storageURL3 + suffix2
        absURL3 = self.storageURL3 + suffix3

        relURL1, storageId1 = \
            storagelib._convertToRelativeURL(absURL1, self.storageName1)
        # Check if the returned storage ID matches the database record
        self.assertEqual(list(storagelib.storageDB.keys()), [ storageId1 ])
        # Check if the created record has correct properties
        storage1 = storagelib.storageDB[storageId1]
        self.assertEqual(storage1['name'], self.storageName1)
        self.assertEqual(storage1['url'], self.storageURL1)
        # Check if the relative URL is correct
        self.assertEqual(relURL1, suffix1)
        # Check if the relative URL is converted back to absolute correctly
        self.assertEqual(
            convertToAbsoluteURL(relURL1, storageId1), absURL1
            )

        relURL2, storageId2 = \
            storagelib._convertToRelativeURL(absURL2, self.storageName2)

        # Check if the database content has been updated properly
        self.assertEqual(
            set(storagelib.storageDB.keys()), set([storageId1, storageId2])
            )
        # Check if the created record has correct properties
        storage2 = storagelib.storageDB[storageId2]
        self.assertEqual(storage2['name'], self.storageName2)
        self.assertEqual(storage2['url'], self.storageURL3)
        # Check if the relative URL is correct
        self.assertEqual(relURL2, suffix2)
        # Check if the relative URL is converted back to absolute correctly
        self.assertEqual(
            convertToAbsoluteURL(relURL2, storageId2), absURL2
            )

        relURL3, storageId3 = \
            storagelib._convertToRelativeURL(absURL3, self.storageName3)

        # Make sure the database content remains the same
        self.assertEqual(
            set(storagelib.storageDB.keys()), set([storageId1, storageId2])
            )
        storage3 = storagelib.storageDB[storageId3]
        # Check if the same record is used as for the previous step
        self.assertEqual(storageId2, storageId3)
        self.assertTrue(storage2 is storage3)
        # Check if the record has its properties unmodified
        self.assertEqual(storage3['name'], self.storageName2)
        self.assertEqual(storage3['url'], self.storageURL3)
        # Check if the relative URL is correct
        self.assertEqual(relURL3, suffix3)
        # Check if the relative URL is converted back to absolute correctly
        self.assertEqual(
            convertToAbsoluteURL(relURL3, storageId3), absURL3
            )

    def test0400TakeOver(self):
        '''Test taking over aliases from another storage.
        '''
        self.addStorage(self.storageId1, self.storageName1, self.storageURL1,
            ( 'alias1', 'alias2' )
            )
        storage2 = self.addStorage(self.storageId2, self.storageName2,
            self.storageURL2, ( 'alias3', 'alias4' )
            )
        storagelib.storageDB[self.storageId1].takeOver(storage2)
        self.assertEqual(
            list(storagelib.storageDB.keys()),
            [self.storageId1]
            )
        self.assertEqual(
            storagelib._storageNames, {self.storageName1: self.storageId1}
            )
        self.assertEqual(
            storagelib._storageURLMap, {self.storageURL1: self.storageId1}
            )
        self.assertEqual(storagelib._storageAliases, {
            'alias1': self.storageId1,
            'alias2': self.storageId1,
            'alias3': self.storageId1,
            'alias4': self.storageId1,
            self.storageId2: self.storageId1,
            })

        # Add one more storage and check the mappings again
        self.addStorage(self.storageId2, self.storageName2, self.storageURL2,
            )

if __name__ == '__main__':
    unittest.main()

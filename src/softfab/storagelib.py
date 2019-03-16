# SPDX-License-Identifier: BSD-3-Clause

from re import compile as re_compile, split as re_split
from typing import Mapping
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
import logging

from softfab.config import dbDir
from softfab.databaselib import (
    Database, DatabaseElem, RecordObserver, createInternalId
)
from softfab.xmlbind import XMLTag
from softfab.xmlgen import xml

_storageNames = {} # type: Mapping[str, str]
_storageURLMap = {} # type: Mapping[str, str]
_storageAliases = {} # type: Mapping[str, str]

class _StorageObserver(RecordObserver):
    def added(self, record):
        record._initData() # pylint: disable=protected-access
    def updated(self, record):
        record._initData() # pylint: disable=protected-access
    def removed(self, record):
        pass

class StorageFactory:
    @staticmethod
    def createStorage(attributes):
        return Storage(attributes)

class StorageDB(Database):
    baseDir = dbDir + '/storages'
    factory = StorageFactory()
    privilegeObject = 'sp'
    description = 'storage'
    uniqueKeys = ( 'id', )
storageDB = StorageDB()
storageDB.addObserver(_StorageObserver())

class Storage(XMLTag, DatabaseElem):
    tagName = 'storage'
    boolProperties = ('export',)

    def __init__(self, attributes, copyFrom = None):
        XMLTag.__init__(self, attributes)
        DatabaseElem.__init__(self)
        if copyFrom is None:
            self.__aliases = set()
        else:
            self.__aliases = set(copyFrom.__aliases) # pylint: disable=protected-access

    def _addAlias(self, attributes):
        alias = attributes['id']
        self.__aliases.add(alias)

    def _endParse(self):
        self._initData()

    def getId(self):
        return self._properties['id']

    def getURL(self):
        return self._properties['url']

    def getExportURL(self):
        url = self._properties['url']
        return urljoin(url, '../export/TaskExport.py' + urlsplit(url).path)

    def hasExport(self):
        return self._properties['export']

    def joinURL(self, url):
        return urljoin(self._properties['url'], url)

    def takeOver(self, other):
        # TODO: Removing the old element and adding the aliases should happen
        #       in a transaction, if our DB had those.
        storageDB.remove(other)
        storageId = self.getId()
        aliases = set(other.__aliases) # pylint: disable=protected-access
        aliases.add(other.getId())
        for alias in aliases:
            _storageAliases[alias] = storageId
        self.__aliases |= aliases
        self._notify()

    def _getContent(self):
        for alias in self.__aliases:
            yield xml.alias(id = alias)

    def _initData(self):
        storageId = self.getId()
        name = self._properties['name']
        if name not in _storageNames:
            _storageNames[name] = storageId
        else:
            logging.warning(
                'Duplicate storage name: \'%s\' (storages: \'%s\', \'%s\')',
                name, _storageNames[name], storageId
                )
        url = self._properties['url']
        if url not in _storageURLMap:
            _storageURLMap[url] = storageId
        else:
            logging.warning(
                'Duplicate storage URL: \'%s\' (storages: \'%s\', \'%s\')',
                url, _storageURLMap[url], storageId
                )
        for alias in self.__aliases:
            _storageAliases[alias] = storageId

    def _retired(self):
        del _storageNames[self._properties['name']]
        del _storageURLMap[self._properties['url']]
        for alias in self.__aliases:
            del _storageAliases[alias]

_reJobDate = re_compile(r'^\d{6}$')
_reJobTimeSeq = re_compile(r'^\d{4}-[0-9A-Fa-f]{4}$')
def _splitReportURL(url):
    scheme, host, path, param, fragm = urlsplit(url, 'http')
    parts = re_split('/+', path)
    jobParts = parts[-4 : -2]
    if len(jobParts) == 2 \
    and _reJobDate.match(jobParts[0]) and _reJobTimeSeq.match(jobParts[1]):
        # Two dirs for job ID (new).
        index = -4
    else:
        # One dir for job ID (old).
        index = -3
    # The trailing slash is needed for 'urljoin' to work correctly later
    base = urlunsplit(
        (scheme.lower(), host.lower(), '/'.join(parts[:index]), '', '')
        ) + '/'
    rel = urlunsplit(('', '', '/'.join(parts[index:]), param, fragm))
    return base, rel

def _convertToRelativeURL(url, runnerId = None):
    # The 'url' must be a non-empty string
    base, rel = _splitReportURL(url)
    storageId = _storageURLMap.get(base)
    if storageId is None:
        storageId = createInternalId()
        if not runnerId:
            storageName = storageId
        elif runnerId in _storageNames:
            storageName = runnerId + '-' + storageId
        else:
            storageName = runnerId
        # In the unlikely case the same name was entered manually
        if storageName in _storageNames:
            suffix = 1
            # Assume we find an unused name before 'suffix' wraps
            while storageName + str(suffix) in _storageNames:
                suffix += 1
            storageName += '-' + str(suffix)
        storageDB.add(Storage( {
            'id': storageId,
            'name': storageName,
            'url': base,
            } ))
    return rel, storageId

def _lookupStorage(storageId):
    '''Looks up a storage object by ID, where ID can be an ID that is still in
    use or an ID of a storage pool that has been merged into another one.
    '''
    return storageDB.get(_storageAliases.get(storageId, storageId))

class StorageURLMixin:

    def __init__(self):
        # TODO: This filters bad URL paths out of the database.
        #       We should also prevent them from going into the database.
        url = self._properties.get('url')
        if url is not None:
            if '%' not in url:
                newURL = quote(url)
                if newURL != url:
                    self._properties['url'] = newURL

    def __getStorage(self):
        storageId = self._properties.get('storage')
        return None if storageId is None else _lookupStorage(storageId)

    def __setURL(self, url):
        assert 'storage' not in self._properties
        if url:
            self._properties['url'], self._properties['storage'] = \
                _convertToRelativeURL(url, self._properties.get('runner'))
        elif url == '':
            self._properties['url'] = ''
        else:
            self._properties.pop('url', None)

    def setURL(self, url):
        if self._properties.get('url'):
            # TODO: Consider raising an exception instead of ignoring of the
            #       new URL silently.
            pass
        else:
            self.__setURL(url)
            self._notify()

    def getURL(self):
        url = self._properties.get('url')
        if not url:
            return url # '' or None
        storage = self.__getStorage()
        if storage is None:
            return None
        return storage.joinURL(url)

    def getExportURL(self):
        url = self._properties.get('url')
        if not url:
            return None
        storage = self.__getStorage()
        if storage is None:
            return None
        return urljoin(storage.getExportURL(), url.rstrip('/'))

    def hasExport(self):
        storage = self.__getStorage()
        return storage is not None and storage.hasExport()

def getStorageIdByName(name):
    return _storageNames.get(name)

def getStorageIdByURL(name):
    return _storageURLMap.get(name)

# The database must be preloaded to fill in the '_storage*' dictionaries.
# It is safe to do, because there are no dependencies on other databases.
storageDB.preload()

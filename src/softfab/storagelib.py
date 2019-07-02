# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from re import compile as re_compile, split as re_split
from typing import (
    TYPE_CHECKING, Dict, Mapping, MutableSet, Optional, Tuple, TypeVar, Union,
    cast
)
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
import logging

from softfab.config import dbDir
from softfab.databaselib import (
    Database, DatabaseElem, RecordObserver, createInternalId
)
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLAttributeValue, XMLContent, xml

_storageNames = {} # type: Dict[str, str]
_storageURLMap = {} # type: Dict[str, str]
_storageAliases = {} # type: Dict[str, str]

StorageRecord = TypeVar('StorageRecord', bound='Storage')

class _StorageObserver(RecordObserver[StorageRecord]):
    def added(self, record: StorageRecord) -> None:
        record._initData() # pylint: disable=protected-access
    def updated(self, record: StorageRecord) -> None:
        record._initData() # pylint: disable=protected-access
    def removed(self, record: StorageRecord) -> None:
        pass

class StorageFactory:
    @staticmethod
    def createStorage(attributes: Mapping[str, XMLAttributeValue]) -> 'Storage':
        return Storage(attributes)

class StorageDB(Database['Storage']):
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

    def __init__(self,
                 attributes: Mapping[str, XMLAttributeValue],
                 copyFrom: Optional['Storage'] = None
                 ):
        XMLTag.__init__(self, attributes)
        DatabaseElem.__init__(self)
        if copyFrom is None:
            self.__aliases = set() # type: MutableSet[str]
        else:
            self.__aliases = set(copyFrom.__aliases) # pylint: disable=protected-access

    def _addAlias(self, attributes: Mapping[str, XMLAttributeValue]) -> None:
        alias = cast(str, attributes['id'])
        self.__aliases.add(alias)

    def _endParse(self) -> None:
        self._initData()

    def getId(self) -> str:
        return cast(str, self._properties['id'])

    def getName(self) -> str:
        return cast(str, self._properties['name'])

    def getURL(self) -> str:
        return cast(str, self._properties['url'])

    def getExportURL(self) -> str:
        url = self.getURL()
        return urljoin(url, '../export/TaskExport.py' + urlsplit(url).path)

    def hasExport(self) -> bool:
        return cast(bool, self._properties['export'])

    def joinURL(self, url: str) -> str:
        return urljoin(self.getURL(), url)

    def takeOver(self, other: 'Storage') -> None:
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

    def _getContent(self) -> XMLContent:
        for alias in self.__aliases:
            yield xml.alias(id = alias)

    def _initData(self) -> None:
        storageId = self.getId()
        name = self.getName()
        idForName = _storageNames.setdefault(name, storageId)
        if idForName != storageId:
            logging.warning(
                'Duplicate storage name: "%s" (storages: "%s", "%s")',
                name, idForName, storageId
                )
        url = self.getURL()
        idForURL = _storageURLMap.setdefault(url, storageId)
        if idForURL != storageId:
            logging.warning(
                'Duplicate storage URL: "%s" (storages: "%s", "%s")',
                url, idForURL, storageId
                )
        for alias in self.__aliases:
            _storageAliases[alias] = storageId

    def _retired(self) -> None:
        del _storageNames[self.getName()]
        del _storageURLMap[self.getURL()]
        for alias in self.__aliases:
            del _storageAliases[alias]

_reJobDate = re_compile(r'^\d{6}$')
_reJobTimeSeq = re_compile(r'^\d{4}-[0-9A-Fa-f]{4}$')
def _splitReportURL(url: str) -> Tuple[str, str]:
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

def _convertToRelativeURL(url: str,
                          runnerId: Optional[str] = None
                          ) -> Tuple[str, str]:
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

def _lookupStorage(storageId: str) -> Optional[Storage]:
    '''Looks up a storage object by ID, where ID can be an ID that is still in
    use or an ID of a storage pool that has been merged into another one.
    '''
    return storageDB.get(_storageAliases.get(storageId, storageId))

class StorageURLMixin:

    if TYPE_CHECKING:
        def _notify(self) -> None: ...

    def __init__(self) -> None:
        if TYPE_CHECKING:
            self._properties = {} # type: Dict[str, Union[str, int, Enum]]

        # TODO: This filters bad URL paths out of the database.
        #       We should also prevent them from going into the database.
        url = cast(Optional[str], self._properties.get('url'))
        if url is not None:
            if '%' not in url:
                newURL = quote(url)
                if newURL != url:
                    self._properties['url'] = newURL

    def __getStorage(self) -> Optional[Storage]:
        storageId = cast(Optional[str], self._properties.get('storage'))
        return None if storageId is None else _lookupStorage(storageId)

    def __setURL(self, url: str) -> None:
        assert 'storage' not in self._properties
        if url:
            runner = cast(Optional[str], self._properties.get('runner'))
            self._properties['url'], self._properties['storage'] = \
                _convertToRelativeURL(url, runner)
        elif url == '':
            self._properties['url'] = ''
        else:
            self._properties.pop('url', None)

    def setInternalStorage(self, path: str) -> None:
        """Use the Control Center's internal storage pool.
        """
        assert 'storage' not in self._properties
        assert 'url' not in self._properties
        self._properties['storage'] = 'sf.cc'
        self._properties['url'] = path
        self._notify()

    def setURL(self, url: str) -> None:
        if self._properties.get('url'):
            # TODO: Consider raising an exception instead of ignoring of the
            #       new URL silently.
            pass
        else:
            self.__setURL(url)
            self._notify()

    def getURL(self) -> Optional[str]:
        url = cast(Optional[str], self._properties.get('url'))
        if not url:
            return url # '' or None
        storage = self.__getStorage()
        if storage is None:
            storageId = cast(Optional[str], self._properties.get('storage'))
            if storageId == 'sf.cc':
                return urljoin('jobs/', url)
            else:
                return None
        return storage.joinURL(url)

    def getExportURL(self) -> Optional[str]:
        url = cast(Optional[str], self._properties.get('url'))
        if not url:
            return None
        storage = self.__getStorage()
        if storage is None:
            return None
        return urljoin(storage.getExportURL(), url.rstrip('/'))

    def hasExport(self) -> bool:
        storage = self.__getStorage()
        return storage is not None and storage.hasExport()

def getStorageIdByName(name: str) -> Optional[str]:
    return _storageNames.get(name)

def getStorageIdByURL(url: str) -> Optional[str]:
    return _storageURLMap.get(url)

# The database must be preloaded to fill in the '_storage*' dictionaries.
# It is safe to do, because there are no dependencies on other databases.
storageDB.preload()

# SPDX-License-Identifier: BSD-3-Clause

from softfab.config import dbAtomicWrites, logChanges
from softfab.utils import abstract, atomicWrite, cachedProperty
from softfab.xmlbind import parse
from softfab.xmlgen import XML

import logging
import os
import os.path
import re
import time
from abc import ABC
from collections.abc import ItemsView, ValuesView
from operator import itemgetter
from typing import (
    Any, Callable, ClassVar, Dict, FrozenSet, Generic, ItemsView as ItemsViewT,
    Iterator, KeysView as KeysViewT, List, Mapping, Optional, Sequence, Set,
    TypeVar, ValuesView as ValuesViewT, cast
    )

# TODO: Use weakref.WeakValueDictionary to ensure value objects which are
#       dropped from the cache but still in use elsewhere returned the next
#       time the corresponding key is requested.
#       This seems straightforward, but has a lot of messy details, so it needs
#       additional unit tests to verify its behaviour.

# Automatically convert non-versioned DB directory to versioned if
# a VersionedDatabase class uses it.
# Turn this on just after upgrading, then disable it again.
autoVersion = False

_changeLogger = logging.getLogger('ControlCenter.datachange')
_changeLogger.setLevel(logging.INFO if logChanges else logging.ERROR)

class ObsoleteRecordError(Exception):
    '''Raised when a record which has no reason for existing anymore is being
    accessed. Used to purge obsolete records during database conversion.
    '''

Record = TypeVar('Record', bound='DatabaseElem')
R2 = TypeVar('R2', bound='DatabaseElem')

class DatabaseElem:
    '''Abstract base class for database elements.
    '''

    def __init__(self: Record) -> None:
        self.__observers = [] # type: List[Callable[[Record], None]]

    def __hash__(self) -> int:
        return hash(self.getId())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.getId() == other.getId()
        else:
            return NotImplemented

    def __ne__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.getId() != other.getId()
        else:
            return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.getId() < other.getId()
        else:
            return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.getId() <= other.getId()
        else:
            return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.getId() > other.getId()
        else:
            return NotImplemented

    def __ge__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.getId() >= other.getId()
        else:
            return NotImplemented

    def __getitem__(self, key: str) -> object:
        raise KeyError(key)

    def getId(self) -> str:
        '''Returns this object's key.
        '''
        raise NotImplementedError

    def toXML(self) -> XML:
        '''Returns an XML tree representation of this object.
        '''
        raise NotImplementedError

    def addObserver(self, observer: Callable[[Record], None]) -> None:
        '''Registers an observer function.
        This function is called when this object's value changes.
        The function should take a single parameter, which is a reference
        to the object that changed.
        TODO: Registering the observers on the object itself has some problems:
        - it is not possible to unload the object from memory without losing
          the knowledge of which observers are registered to it
        - when update() is called on the database, the new object does not
          inherit the observers of the old one
        It is possible to work around these, but maybe it's cleaner to make
        the database class responsible for all observers.
        '''
        self.__observers.append(observer)

    def removeObserver(self, observer: Callable[[Record], None]) -> None:
        '''Unregisters an observer function.
        '''
        self.__observers.remove(observer)

    def _notify(self: Record) -> None:
        '''Notifies all observers of a change in this object.
        '''
        for observer in list(self.__observers):
            observer(self)

    def _unload(self) -> None:
        '''This is called by the database when the element is no longer
        wanted in memory.
        The element may perform necessary cleanup actions here.
        '''

    def _retired(self) -> None:
        '''This is called by the database when the element is removed
        or replaced by a more recent version.
        '''

class RecordObserver(Generic[Record]):
    '''Interface for observing changes to records.
    '''

    def added(self, record: Record) -> None:
        '''Called when a new record was added to a table.
        '''
        raise NotImplementedError

    def removed(self, record: Record) -> None:
        '''Called when a record was removed from a table.
        '''
        raise NotImplementedError

    def updated(self, record: Record) -> None:
        '''Called when an existing record had its contents updated.
        '''
        raise NotImplementedError

class RecordSubjectMixin(Generic[Record]):

    def __init__(self) -> None:
        self._observers = [] # type: List[RecordObserver[Record]]

    def _notifyAdded(self, record: Record) -> None:
        for observer in self._observers:
            observer.added(record)

    def _notifyRemoved(self, record: Record) -> None:
        for observer in self._observers:
            observer.removed(record)

    def _notifyUpdated(self, record: Record) -> None:
        for observer in self._observers:
            observer.updated(record)

    def addObserver(self, observer: RecordObserver[Record]) -> None:
        self._observers.append(observer)

    def removeObserver(self, observer: RecordObserver[Record]) -> None:
        self._observers.remove(observer)

class Database(Generic[Record], RecordSubjectMixin[Record], ABC):
    """Database implemented by a directory containing XML files.
    An element must implement the methods defined in the DatabaseElem class,
    which is also defined in this module.
    In addition, a factory object should be provided, which handles the XML
    root tag(s) in the fashion prescribed by the xmlbind module.
    """

    # Directory in which the records of this database are kept.
    baseDir = abstract # type: ClassVar[str]

    # Parser for the root XML tag.
    factory = abstract # type: ClassVar[object]

    # The object part of privilege strings that apply to this database.
    # See userlib.privileges for details.
    privilegeObject = abstract # type: ClassVar[str]

    # Describes the type of records contained in this database.
    description = abstract # type: ClassVar[str]

    # Indicates whether this database is kept in memory at all times.
    alwaysInMemory = True

    # Indicates whether during conversion the loaded records can be discarded
    # or have to remain in memory.
    keepInMemoryDuringConversion = False

    # Lists the column keys that are unique: every record will have a different
    # value for the listed keys.
    uniqueKeys = () # type: Sequence[str]

    # Cache the unique values for the given column keys.
    # The mechanism which does this is a bit limited: for every loaded record,
    # the set of seen values will be updated. This means that:
    # 1. it will only work for preloaded databases
    # 2. for versioned databases, it will look at both old and recent versions
    # 3. when records are removed, there is no check whether the last use of
    #    a value is removed
    # So basically it works fine for joblib, where it is needed most, but is
    # not guaranteed to work for every database.
    # If we would keep track of how often a value occurs, we could guarantee
    # values disappear from the cache when they no longer occur (fixes 2 + 3).
    # If we would persist the cached unique values, we no longer rely on
    # preloading (fixes 1).
    # Using weak references, 3 could be solved easily, 2 with some additional
    # effort, but 1 could never be solved, so I decided against it.
    cachedUniqueValues = () # type: Sequence[str]

    # Contains optimized value retriever functions for certain column keys.
    keyRetrievers = {} # type: ClassVar[Mapping[str, Callable[[Any], Any]]]

    # Regular expression with defines all valid database keys.
    __reKey = re.compile('^[@A-Za-z0-9+_-][@A-Za-z0-9.+_ -]*$')
    # Regular expression with defines characters disallowed in database keys.
    __reKeySub = re.compile('(?:^[^A-Za-z0-9+_-]|[^A-Za-z0-9.+_ -])')
    # Regular expression for multiple spaces (to be replaced with a single one)
    __reSpaces = re.compile(' {2,}')

    @classmethod
    def retrieverFor(cls, key: str) -> Callable[[Any], Any]:
        return cls.keyRetrievers.get(key) or itemgetter(key)

    def __init__(self) -> None:
        super().__init__()
        if not os.path.exists(self.baseDir):
            os.makedirs(self.baseDir)
        cache = {} # type: Dict[str, Optional[Record]]
        for fileName in os.listdir(self.baseDir):
            if fileName.endswith('.xml'):
                cache[self._keyForFileName(fileName)] = None
        self._cache = cache
        self.__uniqueValuesFor = dict(
            ( key, set() ) for key in self.cachedUniqueValues
            ) # type: Dict[str, Set[object]]
        # Every time you use "self._update", another "instancemethod" object is
        # created. Storing it per database avoids one instance per record.
        self.__updateFunc = self._update

    def __getitem__(self, key: str) -> Record:
        value = self._cache[key]
        if value is None:
            value = cast(Record, parse(self.factory, self._fileNameForKey(key)))
            self._register(key, value)
        return value

    def __iter__(self) -> Iterator[Record]:
        # In most databases all records are cached, so make that quick.
        if self.alwaysInMemory:
            yield from cast(Iterator[Record], self._cache.values())
        else:
            for key, value in self._cache.items():
                if value is None:
                    yield self.__getitem__(key)
                else:
                    yield value

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    @cachedProperty
    def name(self) -> str:
        """Unique identifier for this database, derived from baseDir."""
        return self.baseDir[self.baseDir.rfind('/') + 1 : ]

    def _fileNameForKey(self, key: str) -> str:
        return self.baseDir + '/' + key + '.xml'

    def _keyForFileName(self, fileName: str) -> str:
        # Strip ".xml" extension.
        return fileName[ : -4]

    _getValueToConvert = __getitem__

    def _register(self, key: str, value: Record) -> None:
        value.addObserver(self.__updateFunc)
        self._cache[key] = value
        for colKey, values in self.__uniqueValuesFor.items():
            values.add(value[colKey])

    def _unregister(self, key: str, value: Record, notify: bool = True) -> None:
        value.removeObserver(self.__updateFunc)
        del self._cache[key]
        if notify:
            # pylint: disable=protected-access
            value._retired()
            value._unload()

    def _update(self, value: Record) -> None:
        assert self.get(value.getId()) is value, 'ID "%s"' % value.getId()
        self.update(value)

    def _write(self, key: str, value: Record) -> None:
        path = self._fileNameForKey(key)
        with atomicWrite(path, 'wb', fsync=dbAtomicWrites) as out:
            out.write(
                value.toXML().flattenXML().encode('ascii', 'xmlcharrefreplace')
                )

    def get(self, key: str) -> Optional[Record]:
        if key in self._cache:
            return self[key]
        else:
            return None

    def keys(self) -> KeysViewT[str]:
        return self._cache.keys()

    def values(self) -> ValuesViewT[Record]:
        if self.alwaysInMemory:
            # All values are in the cache.
            return cast(ValuesViewT[Record], self._cache.values())
        else:
            # Load items as they are iterated through.
            # TODO: If you're going to iterate through all items, why not
            #       keep the database in memory at all times?
            #       Maybe we should have separate classes for preloaded and
            #       not preloaded databases, since in practice they support
            #       different operations.
            return _CachedValuesView(self._cache, self.__getitem__)

    def items(self) -> ItemsViewT[str, Record]:
        if self.alwaysInMemory:
            return cast(ItemsViewT[str, Record], self._cache.items())
        else:
            return _CachedItemsView(self._cache, self.__getitem__)

    def uniqueValues(self, column: str) -> FrozenSet[object]:
        '''Returns an immutable set containing all unique values in `column`.
        '''
        if column in self.cachedUniqueValues:
            return frozenset(self.__uniqueValuesFor[column])
        else:
            return frozenset(record[column] for record in self)

    def checkId(self, key: str) -> None:
        '''Check whether the given string is a valid database key.
        Raises KeyError if the key is invalid, with as its first argument a
        message string describing what is invalid about it.
        '''
        # Run custom key checker, if any.
        self._customCheckId(key)

        # Check generic restrictions.
        name = self.description + ' name'
        if len(key) == 0:
            raise KeyError('Empty %s is not allowed' % name)
        elif len(key) > 120:
            # Most modern hard disk file systems seem to have file names of
            # 255 characters maximum. However, for CD-ROMs (which may be used
            # for archiving) there is a limit of 30 characters in ISO9660,
            # 128 characters in Joliet and 197 in Rock Ridge.
            # Since 30 is not enough for us, we'll use 120 as a cutoff.
            # Note that for example database records will have ".xml" appended,
            # so we cannot use 128.
            raise KeyError(
                '%s too long (%d characters)' % (name.capitalize(), len(key))
                )
        elif '  ' in key:
            # Processing of paths containing two consecutive spaces can
            # cause troubles on the Factory PC and it is unlikely that the
            # user really wants two spaces anyway.
            raise KeyError(
                '%s contains two consecutive spaces' % name.capitalize()
                )
        elif key[-1] == ' ':
            # Just like double spaces, a space and the end is confusing and
            # unlikely to be what the user wants.
            raise KeyError('%s ends with a space' % name.capitalize())
        elif self.__reKey.match(key) is None:
            raise KeyError('Invalid character in %s "%s"' % (name, key))

    def _customCheckId(self, key: str) -> None:
        '''This method can be overridden to provide additional restrictions
        on database keys: raise KeyError if the key is invalid, with as its
        first argument a message string describing what is invalid about it.
        The default implementation does nothing.
        '''

    def adjustId(self, key: str, unique: bool = False) -> str:
        """Makes the given string a valid key by replaces certain characters.
        """
        # TODO: take into account the custom key checker if present
        adjusted = self.__reSpaces.sub(
            ' ', self.__reKeySub.sub('_', key.rstrip())
            )
        if unique:
            while adjusted in self._cache:
                adjusted += '_'
        return adjusted

    def add(self, value: Record) -> None:
        """Adds a record to this database.
        If the added record has an invalid ID (see checkId),
        KeyError is raised.
        If the added record has the same ID as an existing record,
        KeyError is raised.
        """
        key = value.getId()
        self.checkId(key)
        if self.get(key) is not None:
            raise KeyError('duplicate ID "%s"' % key)
        self._write(key, value)
        self._register(key, value)

        # Tell observers.
        _changeLogger.info('datachange/%s/add/%s', self.name, key)
        self._notifyAdded(value)

    def remove(self, value: Record) -> None:
        """Removes record from this database.
        Raises KeyError if the ID of the given record does not occur in this
        database.
        """
        key = value.getId()
        # Do lookup from cache first, to trigger KeyError for non-existing IDs.
        cachedValue = self._cache[key]

        os.remove(self._fileNameForKey(key))
        if cachedValue is None:
            # Not registered yet.
            del self._cache[key]
        else:
            # Unregister object.
            self._unregister(key, cachedValue, False)

        # Tell observers.
        _changeLogger.info('datachange/%s/remove/%s', self.name, key)
        self._notifyRemoved(value)

        # pylint: disable=protected-access
        value._retired()
        value._unload()

    def update(self, value: Record) -> None:
        """Register new version of a record.
        Raises KeyError if the key of the given record does not exist.
        """
        key = value.getId()
        oldValue = self.get(key)
        if oldValue is None:
            raise KeyError('unknown ID "%s"' % key)

        # Store new version in database.
        self._write(key, value)
        if oldValue is not value:
            self._unregister(key, oldValue)
            self._register(key, value)

        # Tell observers.
        _changeLogger.info('datachange/%s/update/%s', self.name, key)
        self._notifyUpdated(value)

    def preload(self) -> None:
        for key in self.keys():
            self.__getitem__(key)

    def convert(self, visitor: Optional[Callable[[Record], None]] = None) \
            -> None:
        '''Converts the XML files that store this database's data to a new
        XML format.
        This happens by rewriting every element in the database.
        Make sure you backup your database before using this method,
        because if the new XML format is missing information,
        that information is lost in the conversion.
        The optional visitor is a function that will be called for each
        converted record with that record as its sole argument. It can be
        used to mark a record as obsolete by raising ObsoleteRecordError
        or it can keep track of reachability of other record types.
        '''
        try:
            # TODO: How to handle obsolete records in versioned databases?
            #       Right now none of the versioned DBs have a check for
            #       obsolete records, so it's not an issue yet.
            # We need to iterate over a copy of the keys since we modify the
            # cache inside the loop.
            for key in list(self._cache.keys()):
                try:
                    value = self._getValueToConvert(key)
                except ObsoleteRecordError:
                    logging.warning('Removing obsolete record: %s', key)
                    del self._cache[key]
                    os.remove(self._fileNameForKey(key))
                else:
                    try:
                        if visitor is not None:
                            visitor(value)
                        self._write(key, value)
                    except ObsoleteRecordError:
                        logging.warning('Removing obsolete record: %s', key)
                        self.remove(value)
                    if not self.keepInMemoryDuringConversion:
                        # Do not keep value in memory.
                        value._unload() # pylint: disable=protected-access
                        self._cache[key] = None
        except Exception:
            logging.exception('Exception while processing record: %s', key)
            raise

class VersionedDatabase(Database[Record]):
    """Database implementation which keeps different versions of a record.
    VersionedDatabase provides the semantics of Database,
    except for modification: the only way to change a record
    in a VersionedDatabase is the update() method.
    If you attempt to modify the record object (DatabaseElem) and
    call _notify() on it, you will get a RuntimeError.
    """
    baseDir = abstract # type: ClassVar[str]
    description = abstract # type: ClassVar[str]
    factory = abstract # type: ClassVar[object]
    privilegeObject = abstract # type: ClassVar[str]

    # Implementation notes:
    #
    # latestVersionOf maps unversioned key to versioned key of latest version.
    # __removedRecords maps unversioned keys of removed records to the
    # versioned key of the latest version that existed (the removed version).

    # Number of digits in version string.
    versionDigits = 4

    def __init__(self) -> None:
        # Backwards compatibility.
        if autoVersion and os.path.exists(self.baseDir):
            versioned = False
            for fileName in os.listdir(self.baseDir):
                if ( fileName.endswith('.xml')
                and len(fileName) > (1 + self.versionDigits + 4)
                and fileName[-(1 + self.versionDigits + 4)] == '.'
                and fileName[-(self.versionDigits + 4) : -4].isdigit()
                ):
                    versioned = True
                elif fileName.endswith('.removed'):
                    versioned = True
            if len(os.listdir(self.baseDir)) == 0:
                versioned = True
            if not versioned:
                # Convert to versioned DB.
                for fileName in os.listdir(self.baseDir):
                    if fileName.endswith('.xml'):
                        key = Database._keyForFileName(self, fileName)
                        os.rename(
                            self.baseDir + '/' + key + '.xml', # src
                            self.baseDir + '/' + key + '.'
                                + '0' * self.versionDigits + '.xml', # dst
                            )

        Database.__init__(self)

        latestVersionOf = {} # type: Dict[str, str]
        for versionedKey in self._cache:
            key, version = versionedKey.split('|')
            latest = latestVersionOf.get(key)
            if latest is None or version > latest[-self.versionDigits : ]:
                latestVersionOf[key] = versionedKey

        removedRecords = {}
        for fileName in os.listdir(self.baseDir):
            if fileName.endswith('.removed'):
                key = fileName[ : -len('.removed')]
                removedRecords[key] = latestVersionOf[key]
                del latestVersionOf[key]

        self.__latestVersionOf = latestVersionOf
        self.__removedRecords = removedRecords

    def __getitem__(self, key: str) -> Record:
        # Test the most common path first: key includes version and is cached.
        value = self._cache.get(key)
        if value is not None:
            return value

        value = self.get(key)
        if value is None:
            raise KeyError(key)
        else:
            return value

    def __iter__(self) -> Iterator[Record]:
        for versionedKey in self.__latestVersionOf.values():
            yield self.getVersion(versionedKey)

    def __len__(self) -> int:
        return len(self.__latestVersionOf)

    def __contains__(self, key: str) -> bool:
        return key in self.__latestVersionOf

    def __increaseVersion(self, versionedKey: Optional[str]) -> str:
        # Determine old version.
        if versionedKey is None:
            version = -1 # never existed before
        else:
            version = int(versionedKey[versionedKey.rindex('|') + 1 : ])
        # Compute new version.
        version += 1
        versionStr = str(version).zfill(self.versionDigits)
        if len(versionStr) > self.versionDigits:
            raise RuntimeError('too many versions')
        return versionStr

    def _fileNameForKey(self, key: str) -> str:
        assert '|' in key, '"%s"' % key
        return self.baseDir + '/' + key.replace('|', '.') + '.xml'

    def _fileNameForRemovedKey(self, key: str) -> str:
        assert '|' not in key, '"%s"' % key
        return self.baseDir + '/' + key + '.removed'

    def _keyForFileName(self, fileName: str) -> str:
        key = super()._keyForFileName(fileName)
        # Replace version separator dot by pipe.
        sep = key.rindex('.')
        return key[ : sep] + '|' + key[sep + 1 : ]

    def _update(self, value: Record) -> None:
        raise RuntimeError('modification detected of versioned record')

    def get(self, key: str) -> Optional[Record]:
        # Lookups with versioned keys should be done with getVersion.
        assert '|' not in key, '"%s"' % key

        # Get versioned key of latest version.
        versionedKey = self.__latestVersionOf.get(key)
        if versionedKey is None:
            # Key doesn't exist.
            return None
        else:
            return self.getVersion(versionedKey)

    def getVersion(self, versionedKey: str) -> Record:
        """Get a specific version of a record.
        Raises KeyError if the key does not exist.
        """
        assert '|' in versionedKey, '"%s"' % versionedKey
        value = self._cache[versionedKey]
        if value is None:
            # Key exists, but was not cached yet.
            value = cast(
                Record,
                parse(self.factory, self._fileNameForKey(versionedKey))
                )
            self._register(versionedKey, value)
        return value

    _getValueToConvert = getVersion

    def latestVersion(self, key: str) -> Optional[str]:
        """Gets the versioned key of the latest version or None.
        """
        return self.__latestVersionOf.get(key)

    def keys(self) -> KeysViewT[str]:
        return self.__latestVersionOf.keys()

    def values(self) -> ValuesViewT[Record]:
        return _IndirectValuesView(self.__latestVersionOf, self.getVersion)

    def items(self) -> ItemsViewT[str, Record]:
        return _IndirectItemsView(self.__latestVersionOf, self.getVersion)

    def add(self, value: Record) -> None:
        key = value.getId()
        self.checkId(key)
        if key in self.__latestVersionOf:
            raise KeyError('duplicate ID "%s"' % key)

        # Determine latest existing version.
        latest = self.__removedRecords.get(key)
        resurrected = latest is not None

        # Register new version.
        versionedKey = key + '|' + self.__increaseVersion(latest)
        self._write(versionedKey, value)
        self._register(versionedKey, value)
        self.__latestVersionOf[key] = versionedKey
        if resurrected:
            del self.__removedRecords[key]
            os.remove(self._fileNameForRemovedKey(key))

        # Tell observers.
        _changeLogger.info('datachange/%s/add/%s', self.name, versionedKey)
        self._notifyAdded(value)

    def remove(self, value: Record) -> None:
        key = value.getId()
        if key not in self.__latestVersionOf:
            raise KeyError('unknown ID "%s"' % key)
        versionedKey = self.__latestVersionOf[key]

        with open(self._fileNameForRemovedKey(key), 'w'):
            # File is only a marker, so leave it empty.
            pass
        del self.__latestVersionOf[key]
        self.__removedRecords[key] = versionedKey

        # Tell observers.
        _changeLogger.info('datachange/%s/remove/%s', self.name, versionedKey)
        self._notifyRemoved(value)

        value._retired() # pylint: disable=protected-access

    def update(self, value: Record) -> None:
        key = value.getId()
        oldValue = self.getVersion(self.__latestVersionOf[key])

        # Trap likely error.
        if value is oldValue:
            raise ValueError('duplicate use of record object')
        # Tell the old record it is no longer the latest version.
        oldValue._retired() # pylint: disable=protected-access

        # Store new version in database.
        latest = self.__latestVersionOf[key]
        versionedKey = key + '|' + self.__increaseVersion(latest)
        self._write(versionedKey, value)
        self._register(versionedKey, value)
        self.__latestVersionOf[key] = versionedKey

        # Tell observers.
        _changeLogger.info('datachange/%s/update/%s', self.name, versionedKey)
        self._notifyUpdated(value)

class _CachedValuesView(ValuesView):
    '''A view on mapping values that returns cached values when available.
    '''

    __slots__ = '_lookup',

    def __init__(self, mapping, lookup):
        ValuesView.__init__(self, mapping)
        self._lookup = lookup

    def __iter__(self):
        lookup = self._lookup
        for key, value in self._mapping.items():
            if value is None:
                value = lookup(key)
            yield value

class _CachedItemsView(ItemsView):
    '''A view on mapping items that returns cached values when available.
    '''

    __slots__ = '_lookup',

    def __init__(self, mapping, lookup):
        ItemsView.__init__(self, mapping)
        self._lookup = lookup

    def __iter__(self):
        lookup = self._lookup
        for key, value in self._mapping.items():
            if value is None:
                value = lookup(key)
            yield key, value

class _IndirectValuesView(ValuesView):
    '''A view on mapping values that passes values through a lookup function.
    '''

    __slots__ = '_lookup',

    def __init__(self, mapping, lookup):
        ValuesView.__init__(self, mapping)
        self._lookup = lookup

    def __iter__(self):
        lookup = self._lookup
        for value in self._mapping.values():
            yield lookup(value)

class _IndirectItemsView(ItemsView):
    '''A view on mapping items that passes values through a lookup function.
    '''

    __slots__ = '_lookup',

    def __init__(self, mapping, lookup):
        ItemsView.__init__(self, mapping)
        self._lookup = lookup

    def __iter__(self):
        lookup = self._lookup
        for key, value in self._mapping.items():
            yield key, lookup(value)

class SingletonElem(DatabaseElem):
    '''Base class for singleton records, meaning record which are by definition
    the only record in their database.
    '''

    def getId(self):
        return 'singleton'

    def toXML(self) -> XML:
        # This method is already declared abstract in DatabaseElem, we re-assert
        # that here to please PyLint.
        raise NotImplementedError

class SingletonObserver(RecordObserver):
    '''Base class for observers of singleton tables.
    The subclass only has to implement the updated() method.
    '''

    def added(self, record):
        self.updated(record)

    def removed(self, record):
        assert False, 'singleton instance removed'

    def updated(self, record):
        raise NotImplementedError

class SingletonWrapper:
    '''Wrapper for easy access to the singleton record for databases which
    always contain exactly one record: anything you call on the singleton
    object is forwarded to the record object.
    '''

    def __init__(self, db):
        '''Creates a singleton wrapper for the given database.
        The database must already contain its single record.
        '''
        def updateInstance():
            assert len(db) == 1
            # pylint: disable=attribute-defined-outside-init
            # PyLint does not see that this is called first from the
            # constructor.
            self.__record = db['singleton']

        updateInstance()

        class Observer(SingletonObserver):
            def updated(self, record):
                updateInstance()

        # TODO: For consistency, this observer must be the first one called
        #       when the record is updated. This is true for our current
        #       implementation, but not guaranteed by the interface.
        db.addObserver(Observer())

    def __getattr__(self, name):
        return getattr(self.__record, name)

    def __getitem__(self, name):
        return self.__record[name]

# Regular expression with defines all valid wrapper variable names.
# Under UNIX-like systems, the only universal rule is that a name cannot be
# empty and cannot contain an "=". It is left up to the applications to decide
# what is considered a valid environment variable name. Since environment
# variables will typically be used in a shell, we will accept only characters
# that the major shells accept: letters (upper and lower case), digits and
# underscore, with the first character not a digit.
# I checked in Windows and it accepts all of these characters (and more).
# A difference between UNIX and Windows is that in Windows names are case
# insensitive (case is preserved, but not checked).
# In the scripting languages we support, the names we accept for environment
# variable names are also allowed for variable names.
_reWrapperVarName = re.compile('^[A-Za-z_][A-Za-z0-9_]*$')

def checkWrapperVarName(name: str) -> None:
    '''Checks whether a given name is safe to be used as a name for a wrapper
    variable. If it is safe, nothing happens, otherwise KeyError is raised
    with a message describing what aspect of the name is unsafe.
    '''
    if _reWrapperVarName.match(name) is None:
        if name == '':
            raise KeyError('name must not be empty')
        if name[0].isdigit():
            raise KeyError('name must not start with a digit')
        illegalChars = [] # type: List[str]
        for char in name:
            if not (ord(char) < 128 and (char.isalnum() or char == '_')):
                if char not in illegalChars:
                    illegalChars.append(char)
        raise KeyError(
            'name contains illegal characters: ' + ', '.join(
                '"%s"' % char for char in illegalChars
                )
            )
    if name.upper().startswith('SF_'):
        raise KeyError(
            'the prefix "SF_" is reserved for wrapper variables '
            'set by SoftFab itself'
            )

class _IdCreator:

    def __init__(self):
        self.__lastId = 0

    def __call__(self, internal):
        newId = max(int(time.time() * 1000), self.__lastId + 1)
        self.__lastId = newId
        if internal:
            return '%010X' % (newId - 0x10000000000)
        else:
            return time.strftime(
                '%y%m%d-%H%M', time.localtime(newId / 1000)
                ) + ('-%04X' % (newId % 60000))

_idCreator = _IdCreator()

def createInternalId() -> str:
    return _idCreator(True)

def createUniqueId() -> str:
    return _idCreator(False)

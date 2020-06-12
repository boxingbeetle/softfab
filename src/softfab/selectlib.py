# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from collections import defaultdict
from typing import (
    AbstractSet, Callable, ClassVar, Dict, ItemsView, Iterable, Iterator,
    Mapping, Optional, Sequence, Tuple, TypeVar
)

from softfab.compat import Protocol
from softfab.databaselib import Database, DatabaseElem, RecordObserver
from softfab.utils import abstract
from softfab.xmlgen import XMLNode, xml


class Selectable(Protocol):
    def _getTag(self, tag: str) -> Optional[Mapping[str, str]]:
        raise NotImplementedError
    def _tagItems(self) -> ItemsView[str, Mapping[str, str]]:
        raise NotImplementedError

class Tags(Selectable):

    def __init__(self, cache: 'TagCache') -> None:
        super().__init__()
        self.__cache = cache
        self.__tags: Dict[str, Dict[str, str]] = {}

    def _load(self, key: str, value: str) -> None:
        cvalue, dvalue = self.__cache.toCanonical(key, value, True)
        self.__tags.setdefault(key, {})[cvalue] = dvalue
        #if value != dvalue: "Warning!"

    def toXML(self) -> Iterator[XMLNode]:
        """Serializes tags to XML."""
        for key, values in self.__tags.items():
            for value in values.values():
                yield xml.tag(key = key, value = value)

    def _getTag(self, tag: str) -> Optional[Mapping[str, str]]:
        return self.__tags.get(tag)

    def _tagItems(self) -> ItemsView[str, Mapping[str, str]]:
        return self.__tags.items()

    def getTagKeys(self) -> AbstractSet[str]:
        return set(self.__tags)

    def getTagValues(self, key: str) -> AbstractSet[str]:
        '''Returns the set of display values for the given key.
        '''
        values = self.__tags.get(key)
        if values is None:
            return set()
        else:
            return set(values.values())

    def hasTagKey(self, key: str) -> bool:
        return key in self.__tags

    def hasTagValue(self, key: str, cvalue: str) -> bool:
        # Note: the value must be already in its canonical form
        return cvalue in self.__tags.get(key, ())

    def setTag(self, key: str, values: Iterable[str]) -> None:
        '''Sets the value set for the given key.
        '''
        canonicalValues = dict(
            self.__cache.toCanonical(key, value)
            for value in values
            )
        if canonicalValues:
            self.__tags[key] = canonicalValues
        elif key in self.__tags:
            del self.__tags[key]

    def updateTags(self,
                   changes: Mapping[str, Mapping[str, Optional[str]]]
                   ) -> None:
        '''Updates the tags of this object according to the given change spec.
        The change spec is a dictionary which contains the modifications to
        make for each tag key.
        The modifications are a mapping from canonical value to display value.
        If the display value is None, the tag is removed.
        If the display value is not None, the tag is added or updated.
        '''
        for tagKey, chValues in changes.items():
            values = self.__tags.get(tagKey)
            for cvalue, dvalue in chValues.items():
                if dvalue is None:
                    if values is not None and cvalue in values:
                        del values[cvalue]
                else:
                    if values is None:
                        self.__tags[tagKey] = values = {}
                    values[cvalue] = dvalue

class TagCache:

    def __init__(self,
                 items: Iterable['SelectableRecordABC'],
                 getKeys: Callable[[], Sequence[str]]
                 ):
        super().__init__()
        self.__getKeys = getKeys
        self.__items = items
        self.__tags: Dict[str, Dict[str, str]] = defaultdict(dict)

    def __str__(self) -> str:
        return 'TagCache(%s)' % ', '.join(
            '%s: %s' % (
                key, ', '.join(
                    '%s->%s' % pair
                    for pair in self.__tags.get(key, {}).items()
                    )
                )
            for key in self.__getKeys()
            )

    def __canonical(self, value: str) -> str:
        return value.lower()

    def _refreshCache(self) -> None:
        self.__tags.clear()
        for item in self.__items:
            self._updateCache(item.tags)

    def _updateCache(self, tags: Tags) -> None:
        for key, values in tags._tagItems(): # pylint: disable=protected-access
            if values:
                self.__tags[key].update(values)

    def getKeys(self) -> Sequence[str]:
        return self.__getKeys()

    def getValues(self, key: str) -> Iterable[str]:
        '''Returns the display values for the given tag key.
        '''
        return self.__tags.get(key, {}).values()

    def hasValue(self, key: str, value: str) -> bool:
        '''Returns True iff the given value exists for the given key.
        '''
        values = self.__tags.get(key)
        return values is not None and self.__canonical(value) in values

    def toCanonical(self,
                    key: str,
                    value: str,
                    store: bool = False
                    ) -> Tuple[str, str]:
        '''Returns a pair containing the canonical and display value of the
        given key-value pair.
        If the key-value pair did not exist, the given value is returned as
        the display value.
        If "store" is True, the given value is remembered if the key-value pair
        did not exist.
        '''
        # TODO: Make separate methods for returning canonical only or both?
        cvalue = self.__canonical(value)
        if store:
            dvalue = self.__tags[key].setdefault(cvalue, value)
        else:
            dvalue = self.__tags.get(key, {}).get(cvalue, value)
        return (cvalue, dvalue)

class SelectableRecordABC(DatabaseElem, ABC):
    """Abstract base class for database records that support tagging."""

    cache: ClassVar[TagCache] = abstract
    tags: Tags

    def __init__(self) -> None:
        super().__init__()
        self.tags = Tags(self.cache)

    def _addTag(self, attributes: Mapping[str, str]) -> None:
        key = attributes['key']
        value = attributes['value']
        self.tags._load(key, value) # pylint: disable=protected-access

    # Mark this class as abstract:
    def getId(self) -> str:
        raise NotImplementedError

SelectableRecord = TypeVar('SelectableRecord', bound=SelectableRecordABC)

class ObservingTagCache(TagCache, RecordObserver[SelectableRecord]):

    def __init__(self,
                 db: Database[SelectableRecord],
                 getKeys: Callable[[], Sequence[str]]
                 ):
        super().__init__(db, getKeys)
        db.addObserver(self)

    def added(self, record: SelectableRecord) -> None:
        self._updateCache(record.tags)

    def removed(self, record: SelectableRecord) -> None:
        self._refreshCache()

    def updated(self, record: SelectableRecord) -> None:
        self._refreshCache()

def getCommonTags(tagKeys: Iterable[str],
                  items: Iterable[Selectable]
                  ) -> Mapping[str, Mapping[str, str]]:
    commonTags: Optional[Dict[str, Dict[str, str]]] = None
    for item in items:
        if commonTags is None:
            commonTags = {
                # pylint: disable=protected-access
                tagKey: dict(item._getTag(tagKey) or {})
                for tagKey in tagKeys
                }
        else:
            for tagKey in tagKeys:
                values = item._getTag(tagKey) # pylint: disable=protected-access
                if values:
                    commonVals = commonTags[tagKey] # pylint: disable=unsubscriptable-object
                    for value in list(commonVals.keys()):
                        if value not in values:
                            del commonVals[value]
                else:
                    commonTags[tagKey] = {} # pylint: disable=unsupported-assignment-operation
    if commonTags is None:
        return {}
    else:
        return commonTags

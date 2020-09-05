# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from collections import defaultdict
from typing import (
    AbstractSet, Callable, DefaultDict, Dict, ItemsView, Iterable, Iterator,
    Mapping, Optional, Sequence, Set, TypeVar
)

from typing_extensions import Protocol

from softfab.databaselib import Database, DatabaseElem, RecordObserver
from softfab.xmlgen import XMLNode, xml


class Selectable(Protocol):
    def _getTag(self, tag: str) -> Optional[AbstractSet[str]]:
        raise NotImplementedError
    def _tagItems(self) -> ItemsView[str, AbstractSet[str]]:
        raise NotImplementedError

class Tags(Selectable):

    def __init__(self) -> None:
        super().__init__()
        self.__tags: Dict[str, Set[str]] = {}

    def _load(self, key: str, value: str) -> None:
        try:
            tagsForKey = self.__tags[key]
        except KeyError:
            self.__tags[key] = tagsForKey = set()
        tagsForKey.add(value)

    def toXML(self) -> Iterator[XMLNode]:
        """Serializes tags to XML."""
        for key, values in self.__tags.items():
            for value in values:
                yield xml.tag(key=key, value=value)

    def _getTag(self, tag: str) -> Optional[AbstractSet[str]]:
        return self.__tags.get(tag)

    def _tagItems(self) -> ItemsView[str, AbstractSet[str]]:
        return self.__tags.items()

    def getTagKeys(self) -> AbstractSet[str]:
        return set(self.__tags)

    def getTagValues(self, key: str) -> AbstractSet[str]:
        """Returns the set of values for the given key."""
        try:
            return self.__tags[key]
        except KeyError:
            return frozenset()

    def hasTagKey(self, key: str) -> bool:
        return key in self.__tags

    def hasTagValue(self, key: str, value: str) -> bool:
        return value in self.__tags.get(key, ())

    def setTag(self, key: str, values: Iterable[str]) -> None:
        """Sets the value set for the given key."""
        values = set(values)
        if values:
            self.__tags[key] = values
        elif key in self.__tags:
            del self.__tags[key]

    def updateTags(self,
                   tagKey: str,
                   additions: AbstractSet[str],
                   removals: AbstractSet[str]
                   ) -> None:
        """Updates the tag values for the given key according to the given
        change specs.
        """
        values = self.__tags.get(tagKey)
        if values is None:
            self.__tags[tagKey] = values = set()
        values -= removals
        values |= additions

class TagCache:

    def __init__(self,
                 items: Iterable['SelectableRecordABC'],
                 getKeys: Callable[[], Sequence[str]]
                 ):
        super().__init__()
        self.__getKeys = getKeys
        self.__items = items
        self.__tags: DefaultDict[str, Set[str]] = defaultdict(set)

    def __str__(self) -> str:
        return 'TagCache(%s)' % ', '.join(
            '%s: %s' % (key, ', '.join(self.__tags.get(key, ())))
            for key in self.__getKeys()
            )

    def _load(self, key: str, value: str) -> None:
        self.__tags[key].add(value)

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
        return self.__tags.get(key, ())

    def hasValue(self, key: str, value: str) -> bool:
        '''Returns True iff the given value exists for the given key.
        '''
        values = self.__tags.get(key)
        return values is not None and value in values

class SelectableRecordABC(DatabaseElem, ABC):
    """Abstract base class for database records that support tagging."""

    tags: Tags

    def __init__(self) -> None:
        super().__init__()
        self.tags = Tags()

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
                  ) -> Mapping[str, AbstractSet[str]]:
    commonTags: Optional[Dict[str, Set[str]]] = None
    for item in items:
        if commonTags is None:
            commonTags = {
                # pylint: disable=protected-access
                tagKey: set(item._getTag(tagKey) or ())
                for tagKey in tagKeys
                }
        else:
            for tagKey in tagKeys:
                values = item._getTag(tagKey) # pylint: disable=protected-access
                commonVals = commonTags[tagKey] # pylint: disable=unsubscriptable-object
                if values:
                    commonVals.intersection_update(values)
                else:
                    commonVals.clear()
    if commonTags is None:
        return {}
    else:
        return commonTags

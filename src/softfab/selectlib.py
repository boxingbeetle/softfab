# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from collections import defaultdict
from typing import ClassVar

from softfab.databaselib import RecordObserver
from softfab.utils import abstract
from softfab.xmlgen import xml

class Selectable(ABC):
    cache = abstract # type: ClassVar[TagCache]

    def __init__(self):
        self.__tags = {}

    def _addTag(self, attributes):
        key = attributes['key']
        value = attributes['value']
        cvalue, dvalue = self.cache.toCanonical(key, value, True)
        self.__tags.setdefault(key, {})[cvalue] = dvalue
        #if value != dvalue: "Warning!"

    def _tagsAsXML(self):
        '''Serializes tags to XML to store them in the database.
        '''
        for key, values in self.__tags.items():
            for value in values.values():
                yield xml.tag(key = key, value = value)

    def _getTag(self, tag):
        return self.__tags.get(tag)

    def _tagItems(self):
        return self.__tags.items()

    def getTagKeys(self):
        return set(self.__tags)

    def getTagValues(self, key):
        '''Returns the set of display values for the given key.
        '''
        values = self.__tags.get(key)
        if values is None:
            return set()
        else:
            return set(values.values())

    def hasTagKey(self, key):
        return key in self.__tags

    def hasTagValue(self, key, cvalue):
        # Note: the value must be already in its canonical form
        return cvalue in self.__tags.get(key, ())

    def setTag(self, key, values):
        '''Sets the value set for the given key.
        '''
        if values:
            self.__tags[key] = dict(
                self.cache.toCanonical(key, value)
                for value in values
                )
        elif key in self.__tags:
            del self.__tags[key]

    def updateTags(self, changes):
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

    def __init__(self, items, getKeys):
        self.__getKeys = getKeys
        self.__items = items
        self.__tags = defaultdict(dict)

    def __str__(self):
        return 'TagCache(%s)' % ', '.join(
            '%s: %s' % (
                key, ', '.join(
                    '%s->%s' % pair
                    for pair in self.__tags.get(key, {}).items()
                    )
                )
            for key in self.__getKeys()
            )

    def __canonical(self, value):
        return value.lower()

    def _refreshCache(self):
        self.__tags.clear()
        for item in self.__items:
            self._updateCache(item)

    def _updateCache(self, item):
        for key, values in item._tagItems(): # pylint: disable=protected-access
            if values:
                self.__tags[key].update(values)

    def getKeys(self):
        return self.__getKeys()

    def getValues(self, key):
        '''Returns the display values for the given tag key.
        '''
        # TODO: Cache the sorted value list?
        #       Or don't sort here at all?
        return sorted(self.__tags.get(key, {}).values())

    def hasValue(self, key, value):
        '''Returns True iff the given value exists for the given key.
        '''
        values = self.__tags.get(key)
        return values is not None and self.__canonical(value) in values

    def toCanonical(self, key, value, store = False):
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

class ObservingTagCache(TagCache, RecordObserver):

    def __init__(self, db, getKeys):
        TagCache.__init__(self, db, getKeys)
        RecordObserver.__init__(self)
        db.addObserver(self)

    def added(self, record):
        self._updateCache(record)

    def removed(self, record):
        self._refreshCache()

    def updated(self, record):
        self._refreshCache()

def getCommonTags(tagKeys, items):
    commonTags = None
    for item in items:
        if commonTags is None:
            commonTags = dict(
                # pylint: disable=protected-access
                ( tagKey, dict(item._getTag(tagKey) or {}) )
                for tagKey in tagKeys
                )
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
    return commonTags

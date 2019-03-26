# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, cast

from softfab.config import dbDir
from softfab.databaselib import DatabaseElem, VersionedDatabase
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLAttributeValue, XMLContent, xml


class ResTypeFactory:
    @staticmethod
    def createRestype(attributes: Mapping[str, str]) -> 'ResType':
        return ResType(attributes)

class ResTypeDB(VersionedDatabase['ResType']):
    baseDir = dbDir + '/restypes'
    factory = ResTypeFactory()
    privilegeObject = 'rt'
    description = 'resource type'
    uniqueKeys = ( 'name', )

resTypeDB = ResTypeDB()

class ResType(XMLTag, DatabaseElem):
    '''Represents a resource type with the properties common for all resources.
    '''
    tagName = 'restype'
    boolProperties = ('perjob', 'pertask')

    @staticmethod
    def create(name: str,
               pertask: bool,
               perjob: bool,
               description: str = ''
               ) -> 'ResType':
        if name.startswith('sf.'):
            description = {
                taskRunnerResourceTypeName: 'SoftFab task execution agent',
                }[name]
        resType = ResType(dict(
            name=name, pertask=pertask, perjob=perjob
            ))
        # pylint: disable=protected-access
        resType.__description = description
        return resType

    def __init__(self, properties: Mapping[str, XMLAttributeValue]):
        XMLTag.__init__(self, properties)
        DatabaseElem.__init__(self)
        self.__description = ''

    def __getitem__(self, key: str) -> object:
        if key == 'presentation':
            return self.presentationName
        else:
            return super().__getitem__(key)

    def _textDescription(self, text: str) -> None:
        self.__description = text

    @property
    def presentationName(self) -> str:
        name = cast(str, self._properties['name'])
        if name.startswith('sf.'):
            return {
                taskRunnerResourceTypeName: 'Task Runner',
                }[name]
        else:
            return name

    def getId(self) -> str:
        return cast(str, self._properties['name'])

    def getDescription(self) -> str:
        return self.__description

    def _getContent(self) -> XMLContent:
        if self.__description:
            yield xml.description[ self.__description ]

taskRunnerResourceTypeName = 'sf.tr'

if taskRunnerResourceTypeName not in resTypeDB:
    resTypeDB.add(ResType.create(
        taskRunnerResourceTypeName, pertask=True, perjob=False
        ))

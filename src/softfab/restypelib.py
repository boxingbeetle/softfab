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

taskRunnerResourceTypeName = 'sf.tr'
repoResourceTypeName = 'sf.repo'

class ResTypeDB(VersionedDatabase['ResType']):
    factory = ResTypeFactory()
    privilegeObject = 'rt'
    description = 'resource type'
    uniqueKeys = ( 'name', )

    def _postLoad(self) -> None:
        super()._postLoad()

        if taskRunnerResourceTypeName not in self:
            self.add(ResType.create(
                taskRunnerResourceTypeName, pertask=True, perjob=False
                ))

        if repoResourceTypeName not in self:
            self.add(ResType.create(
                repoResourceTypeName, pertask=False, perjob=False
                ))

resTypeDB = ResTypeDB(dbDir / 'restypes')

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
                repoResourceTypeName: 'Version control repository',
                }[name]
        resType = ResType(dict(
            name=name, pertask=pertask, perjob=perjob
            ))
        # pylint: disable=protected-access
        resType.__description = description
        return resType

    def __init__(self, properties: Mapping[str, XMLAttributeValue]):
        super().__init__(properties)
        self.__description = ''

    def __getitem__(self, key: str) -> object:
        if key == 'presentationName':
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
                repoResourceTypeName: 'Repository',
                }[name]
        else:
            return name

    def getId(self) -> str:
        return cast(str, self._properties['name'])

    @property
    def description(self) -> str:
        return self.__description

    def _getContent(self) -> XMLContent:
        if self.__description:
            yield xml.description[ self.__description ]

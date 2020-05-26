# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
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

reservedResourceTypeDescriptions = {
    taskRunnerResourceTypeName: 'SoftFab task execution agent',
    repoResourceTypeName: 'Version control repository',
    }

class ResTypeDB(VersionedDatabase['ResType']):
    privilegeObject = 'rt'
    description = 'resource type'
    uniqueKeys = ( 'name', )

    def __init__(self, baseDir: Path):
        super().__init__(baseDir, ResTypeFactory())

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

# TODO: This should be moved to restypeview, but that is only possible
#       after we replace the __getitem__ mechanism.
def presentResTypeName(name: str) -> str:
    if name.startswith('sf.'):
        return {
            taskRunnerResourceTypeName: 'Task Runner',
            repoResourceTypeName: 'Repository',
            }[name]
    else:
        return name

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
            return presentResTypeName(self.getId())
        else:
            return super().__getitem__(key)

    def _textDescription(self, text: str) -> None:
        self.__description = text

    def getId(self) -> str:
        return cast(str, self._properties['name'])

    @property
    def description(self) -> str:
        name = self.getId()
        if name.startswith('sf.'):
            return reservedResourceTypeDescriptions[name]
        else:
            return self.__description

    def _getContent(self) -> XMLContent:
        if self.__description:
            yield xml.description[ self.__description ]

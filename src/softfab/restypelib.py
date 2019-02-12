# SPDX-License-Identifier: BSD-3-Clause

from softfab.config import dbDir
from softfab.databaselib import VersionedDatabase, DatabaseElem
from softfab.xmlbind import XMLTag
from softfab.xmlgen import xml

class ResTypeFactory:
    @staticmethod
    def createRestype(attributes):
        return ResType(attributes)

class ResTypeDB(VersionedDatabase):
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
    def create(name, pertask, perjob, description=''):
        properties = dict(name=name, pertask=pertask, perjob=perjob)
        if name.startswith('sf.'):
            description = {
                taskRunnerResourceTypeName: 'SoftFab task execution agent',
                }[name]
        resType = ResType(properties)
        # pylint: disable=protected-access
        resType.__description = description
        return resType

    def __init__(self, properties):
        XMLTag.__init__(self, properties)
        DatabaseElem.__init__(self)
        self.__description = ''

    def __getitem__(self, key):
        if key == 'presentation':
            name = self._properties['name']
            if name.startswith('sf.'):
                return {
                    taskRunnerResourceTypeName: 'Task Runner',
                    }[name]
            else:
                return name
        return super().__getitem__(key)

    def _textDescription(self, text):
        self.__description = text

    def getId(self):
        return self._properties['name']

    def getDescription(self):
        return self.__description

    def _getContent(self):
        if self.__description:
            yield xml.description[ self.__description ]

taskRunnerResourceTypeName = 'sf.tr'

if taskRunnerResourceTypeName not in resTypeDB:
    resTypeDB.add(ResType.create(
        taskRunnerResourceTypeName, pertask=True, perjob=False
        ))

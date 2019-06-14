# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, Optional, cast

from softfab import frameworklib
from softfab.config import dbDir
from softfab.databaselib import VersionedDatabase
from softfab.paramlib import GetParent
from softfab.selectlib import ObservingTagCache
from softfab.xmlgen import XMLAttributeValue, XMLContent, xml


class TaskDefFactory:
    @staticmethod
    def createTaskdef(attributes: Mapping[str, str]) -> 'TaskDef':
        return TaskDef(attributes)

class TaskDefDB(VersionedDatabase['TaskDef']):
    baseDir = dbDir + '/taskdefs'
    factory = TaskDefFactory()
    privilegeObject = 'td'
    description = 'task definition'
    uniqueKeys = ( 'id', )
taskDefDB = TaskDefDB()

class TaskDef(frameworklib.TaskDefBase):
    cache = ObservingTagCache(taskDefDB, lambda: ('sf.req',) )

    @staticmethod
    def create(name: str,
               parent: Optional[str] = None,
               title: str = '',
               description: str = ''
               ) -> 'TaskDef':
        properties = dict(
            id = name,
            parent = parent,
            )
        taskDef = TaskDef(properties)
        # pylint: disable=protected-access
        taskDef.__title = title
        taskDef.__description = description
        return taskDef

    def __init__(self, properties: Mapping[str, XMLAttributeValue]):
        frameworklib.TaskDefBase.__init__(self, properties)
        self.__title = ''
        self.__description = ''

    def __getitem__(self, key: str) -> object:
        if key == 'title':
            return self.__title or self.getId()
        elif key == 'description':
            return self.__description or '(no description)'
        else:
            return super().__getitem__(key)

    def _textTitle(self, text: str) -> None:
        self.__title = text

    def _textDescription(self, text: str) -> None:
        self.__description = text

    def getFramework(self,
            getParent: GetParent = frameworklib.frameworkDB.__getitem__
            ) -> frameworklib.Framework:
        frameworkId = cast(str, self['parent'])
        return cast(frameworklib.Framework, getParent(frameworkId))

    def getTitle(self) -> str:
        return self.__title

    def getDescription(self) -> str:
        return self.__description

    @property
    def timeoutMins(self) -> Optional[int]:
        '''Task execution timeout in minutes, or None for never.
        The timeout is stored in the special property "sf.timeout".
        This must not be called on frozen task definitions;
        look up the timeout from the run instead.
        '''
        timeout = self.getParameter('sf.timeout')
        return None if timeout is None else int(timeout)

    def _getContent(self) -> XMLContent:
        yield super()._getContent()
        yield xml.title[ self.__title ]
        yield xml.description[ self.__description ]
        yield self._tagsAsXML()

# Force loading of DB, so TagCache is filled with all existing tag values.
# TODO: Is there an alternative for taskDefDB.preload()?
taskDefDB.preload()

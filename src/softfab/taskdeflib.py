# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
from typing import Mapping, Optional, cast

from softfab.config import dbDir
from softfab.databaselib import VersionedDatabase
from softfab.frameworklib import Framework, FrameworkDB, TaskDefBase
from softfab.paramlib import GetParent, Parameterized, paramTop
from softfab.xmlgen import XMLContent, xml


class TaskDef(TaskDefBase):

    def __init__(self,
                 properties: Mapping[str, Optional[str]],
                 frameworkDB: FrameworkDB
                 ):
        super().__init__(properties)
        self.__frameworkDB = frameworkDB
        self._title = ''
        self._description = ''

    def __getitem__(self, key: str) -> object:
        if key == 'title':
            return self._title or self.getId()
        elif key == 'description':
            return self._description or '(no description)'
        else:
            return super().__getitem__(key)

    def _textTitle(self, text: str) -> None:
        self._title = text

    def _textDescription(self, text: str) -> None:
        self._description = text

    @property
    def frameworkId(self) -> Optional[str]:
        return cast(Optional[str], self._properties.get('parent'))

    def getFramework(self, getParent: Optional[GetParent] = None) -> Framework:
        frameworkId = self.frameworkId
        if frameworkId is None:
            # The framework can be undefined in records that are still being
            # edited; records in the DB must have a framework.
            raise ValueError('getFramework() called on parentless taskdef')
        else:
            return cast(Framework, self.getParent(getParent))

    def getParent(self, getFunc: Optional[GetParent]) -> Parameterized:
        frameworkId = self.frameworkId
        if frameworkId is None:
            return paramTop
        elif getFunc is None:
            return self.__frameworkDB[frameworkId]
        else:
            return getFunc(frameworkId)

    def getTitle(self) -> str:
        return self._title

    def getDescription(self) -> str:
        return self._description

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
        yield xml.title[ self._title ]
        yield xml.description[ self._description ]

class TaskDefFactory:

    frameworkDB: FrameworkDB

    def createTaskdef(self, attributes: Mapping[str, str]) -> TaskDef:
        return TaskDef(attributes, self.frameworkDB)

    def newTaskDef(self,
                   name: str,
                   parent: Optional[str] = None,
                   title: str = '',
                   description: str = ''
                   ) -> TaskDef:
        properties = dict(id=name, parent=parent)
        taskDef = TaskDef(properties, self.frameworkDB)
        # pylint: disable=protected-access
        taskDef._title = title
        taskDef._description = description
        return taskDef

class TaskDefDB(VersionedDatabase[TaskDef]):
    privilegeObject = 'td'
    description = 'task definition'
    uniqueKeys = ( 'id', )

    factory: TaskDefFactory

    def __init__(self, baseDir: Path):
        super().__init__(baseDir, TaskDefFactory())

taskDefDB = TaskDefDB(dbDir / 'taskdefs')

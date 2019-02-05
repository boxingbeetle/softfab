# SPDX-License-Identifier: BSD-3-Clause

import frameworklib
from config import dbDir
from databaselib import VersionedDatabase
from selectlib import Selectable, ObservingTagCache
from xmlgen import xml

class TaskDefFactory:
    @staticmethod
    def createTaskdef(attributes):
        return TaskDef(attributes)

class TaskDefDB(VersionedDatabase):
    baseDir = dbDir + '/taskdefs'
    factory = TaskDefFactory()
    privilegeObject = 'td'
    description = 'task definition'
    uniqueKeys = ( 'id', )
taskDefDB = TaskDefDB()

class TaskDef(frameworklib.TaskDefBase, Selectable):
    cache = ObservingTagCache(taskDefDB, lambda: ('sf.req',) )

    @staticmethod
    def create(name, parent = None, title = '', description = ''):
        properties = dict(
            id = name,
            parent = parent,
            )
        taskDef = TaskDef(properties)
        # pylint: disable=protected-access
        taskDef.__title = title
        taskDef.__description = description
        return taskDef

    def __init__(self, properties):
        frameworklib.TaskDefBase.__init__(self, properties)
        Selectable.__init__(self)
        self.__title = ''
        self.__description = ''

    def __getitem__(self, key):
        if key == 'title':
            return self.__title or self.getId()
        elif key == 'description':
            return self.__description or '(no description)'
        else:
            return super().__getitem__(key)

    def _textTitle(self, text):
        self.__title = text

    def _textDescription(self, text):
        self.__description = text

    def getFramework(self, getParent = frameworklib.frameworkDB.__getitem__):
        return getParent(self['parent'])

    def getTitle(self):
        return self.__title

    def getDescription(self):
        return self.__description

    @property
    def timeoutMins(self):
        '''Task execution timeout in minutes, or None for never.
        The timeout is stored in the special property "sf.timeout".
        This must not be called on frozen task definitions;
        look up the timeout from the run instead.
        '''
        timeout = self.getParameter('sf.timeout')
        return None if timeout is None else int(timeout)

    def _getContent(self):
        yield from super()._getContent()
        yield xml.title[ self.__title ]
        yield xml.description[ self.__description ]
        yield self._tagsAsXML()

# Force loading of DB, so TagCache is filled with all existing tag values.
# TODO: Is there an alternative for taskDefDB.preload()?
taskDefDB.preload()

# SPDX-License-Identifier: BSD-3-Clause

from abc import abstractmethod
from typing import (
    Callable, ClassVar, Collection, Iterator, Optional, Tuple, cast
)

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.configlib import Config, ConfigDB
from softfab.configview import ConfigTable, SimpleConfigTable
from softfab.datawidgets import DataColumn, DataTable
from softfab.formlib import checkBox
from softfab.pageargs import IntArg, SortArg
from softfab.projectlib import project
from softfab.request import Request
from softfab.selectview import BasketArgs, SelectProcMixin, selectDialog
from softfab.userlib import User, UserDB, checkPrivilege
from softfab.webgui import docLink
from softfab.xmlgen import XMLContent, xhtml


class SelectColumn(DataColumn[Config]):
    keyName = None
    label = None

    def presentCell(self, record: Config, **kwargs: object) -> XMLContent:
        selectName = cast(str, kwargs['selectName'])
        selectFunc = cast(Callable[[str], Tuple[bool, bool]],
                          kwargs['selectFunc'])
        recordId = record.getId()
        checked, enabled = selectFunc(recordId)
        return checkBox(
            name=selectName, value=recordId, checked=checked,
            disabled=not enabled
            )

class BaseTagConfigTable(ConfigTable):
    showConflictAsError = True

    def _simpleMode(self, proc: 'LoadExecute_GET.Processor') -> bool:
        raise NotImplementedError

    def iterRowStyles(self,
                      rowNr: int,
                      record: Config,
                      **kwargs: object
                      ) -> Iterator[str]:
        getRowStyle = cast(Callable[[Config], Optional[str]],
                           kwargs.pop('getRowStyle'))
        yield from super().iterRowStyles(rowNr, record, **kwargs)
        style = getRowStyle(record)
        if style is not None:
            yield style

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn[Config]]:
        proc = cast(LoadExecute_GET.Processor, kwargs['proc'])
        tableClass = (
            SimpleConfigTable if self._simpleMode(proc) else ConfigTable
            )
        yield SelectColumn.instance
        yield from tableClass.iterColumns(self, **kwargs)

class TagConfigTable(BaseTagConfigTable):

    def _simpleMode(self, proc: 'LoadExecute_GET.Processor') -> bool:
        # If there is a basket, use simple mode, otherwise full mode.
        return len(proc.tagCache.getKeys()) != 0 and len(proc.selected) > 0

    def getRecordsToQuery(self,
                          proc: PageProcessor['LoadExecute_GET.Arguments']
                          ) -> Collection[Config]:
        return cast(LoadExecute_GET.Processor, proc).filteredRecords

class BasketConfigTable(BaseTagConfigTable):
    sortField = 'sort_basket'
    tabOffsetField = None

    def _simpleMode(self, proc: 'LoadExecute_GET.Processor') -> bool:
        return True

    def getRecordsToQuery(self,
                          proc: PageProcessor['LoadExecute_GET.Arguments']
                          ) -> Collection[Config]:
        return cast(LoadExecute_GET.Processor, proc).selectedRecords

class LoadExecute_GET(FabPage['LoadExecute_GET.Processor',
                              'LoadExecute_GET.Arguments']):
    icon = 'IconExec'
    description = 'Execute'
    children = [
        'Execute', 'DelJobConfig', 'FastExecute', 'BatchExecute', 'ConfigTags',
        'ConfigDetails'
        ]

    class Arguments(BasketArgs):
        first = IntArg(0)
        sort = SortArg()
        sort_basket = SortArg()

    class Processor(PageProcessor[Arguments],
                    SelectProcMixin[Arguments, Config]):

        configDB: ClassVar[ConfigDB]
        userDB: ClassVar[UserDB]

        @property
        @abstractmethod
        def db(self) -> ConfigDB:
            return self.configDB

        def iterActions(self) -> Iterator[Tuple[str, str, str]]:
            if project.getTagKeys():
                yield 'tags', 'Edit Tags...', 'ConfigTags'
            yield 'execute', 'Execute...', 'BatchExecute'

        async def process(self,
                          req: Request['LoadExecute_GET.Arguments'],
                          user: User
                          ) -> None:
            self.processSelection()

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Config]]:
        yield TagConfigTable.instance
        yield BasketConfigTable.instance

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'c/l')

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(LoadExecute_GET.Processor, kwargs['proc'])
        yield xhtml.h2[ 'Execute from Configuration' ],
        yield selectDialog(
            self.name, proc.tagCache,
            TagConfigTable.instance, BasketConfigTable.instance,
            'Configurations to Tag or Execute',
            **kwargs
            )
        yield xhtml.p[
            'Read here more about: ',
            docLink('/start/user_manual/#execute')[
                'Execute from Configuration'
                ]
            ]

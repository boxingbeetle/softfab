# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import DataTable
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.shadowlib import shadowDB
from softfab.shadowview import ShadowTable, trimPolicy
from softfab.userlib import IUser, checkPrivilege
from softfab.webgui import WidgetT
from softfab.xmlgen import XMLContent


class ShadowQueue_GET(FabPage['ShadowQueue_GET.Processor', 'ShadowQueue_GET.Arguments']):
    icon = 'TaskRunStat1'
    description = 'Shadow Queue'

    @staticmethod
    def isActive():
        return len(shadowDB) > 0

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):
        pass

    def checkAccess(self, user: IUser) -> None:
        checkPrivilege(user, 'sh/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield ShadowTable.instance

    def iterWidgets(self, proc: Processor) -> Iterator[WidgetT]:
        yield ShadowTable

    def presentContent(self, proc: Processor) -> XMLContent:
        yield trimPolicy
        yield ShadowTable.instance.present(proc=proc)

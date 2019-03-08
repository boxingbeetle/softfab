# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import DataTable
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.shadowlib import shadowDB
from softfab.shadowview import ShadowTable, trimPolicy
from softfab.webgui import WidgetT

class ShadowQueue_GET(FabPage['ShadowQueue_GET.Processor']):
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

    def checkAccess(self, req):
        req.checkPrivilege('sh/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield ShadowTable.instance

    def iterWidgets(self, proc: Processor) -> Iterator[WidgetT]:
        yield ShadowTable

    def presentContent(self, proc):
        yield trimPolicy
        yield ShadowTable.instance.present(proc=proc)

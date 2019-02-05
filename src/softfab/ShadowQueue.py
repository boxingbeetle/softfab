# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from Page import PageProcessor
from pageargs import IntArg, PageArgs, SortArg
from shadowlib import shadowDB
from shadowview import ShadowTable, trimPolicy

class ShadowQueue(FabPage):
    icon = 'TaskRunStat1'
    description = 'Shadow Queue'
    isActive = staticmethod(lambda: len(shadowDB) > 0)

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):
        pass

    def checkAccess(self, req):
        req.checkPrivilege('sh/l')

    def iterDataTables(self, proc):
        yield ShadowTable.instance

    def iterWidgets(self, proc):
        yield ShadowTable

    def presentContent(self, proc):
        yield trimPolicy
        yield ShadowTable.instance.present(proc=proc)

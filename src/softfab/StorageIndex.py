# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from Page import PageProcessor
from pageargs import IntArg, PageArgs, SortArg
from storageview import StorageTable

class StorageIndex(FabPage):
    icon = 'IconReport'
    description = 'Report Storages'
    children = [ 'StorageEdit' ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):
        pass

    def checkAccess(self, req):
        req.checkPrivilege('sp/l', 'view the storage list')

    def iterDataTables(self, proc):
        yield StorageTable.instance

    def presentContent(self, proc):
        return StorageTable.instance.present(proc=proc)

# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import DataTable
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.storageview import StorageTable

class StorageIndex_GET(FabPage['StorageIndex_GET.Processor']):
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

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield StorageTable.instance

    def presentContent(self, proc):
        return StorageTable.instance.present(proc=proc)

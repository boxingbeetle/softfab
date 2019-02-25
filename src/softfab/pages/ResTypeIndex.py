# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import (
    BoolDataColumn, DataColumn, DataTable, LinkColumn
    )
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.restypelib import resTypeDB

class ResTypeLinkColumn(LinkColumn):

    def presentCell(self, record, **kwargs):
        if record.getId().startswith('sf.'):
            return '-'
        else:
            return super().presentCell(record, **kwargs)

class ResTypeTable(DataTable):
    db = resTypeDB
    columns = (
        DataColumn(keyName = 'presentation'),
        BoolDataColumn(keyName = 'pertask', label = 'Per Task'),
        BoolDataColumn(keyName = 'perjob', label = 'Per Job'),
        ResTypeLinkColumn('Edit', 'ResTypeEdit'),
        ResTypeLinkColumn('Delete', 'ResTypeDelete'),
        )

class ResTypeIndex_GET(FabPage):
    icon = 'IconResources'
    description = 'Resource Types'
    children = [ 'ResTypeEdit', 'ResTypeDelete' ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):
        pass

    def checkAccess(self, req):
        req.checkPrivilege('rt/l')

    def iterDataTables(self, proc):
        yield ResTypeTable.instance

    def presentContent(self, proc):
        return ResTypeTable.instance.present(proc=proc)

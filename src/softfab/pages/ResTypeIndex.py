# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import (
    BoolDataColumn, DataColumn, DataTable, LinkColumn
)
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.restypelib import resTypeDB
from softfab.userlib import IUser, checkPrivilege
from softfab.xmlgen import XMLContent


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

class ResTypeIndex_GET(FabPage['ResTypeIndex_GET.Processor', 'ResTypeIndex_GET.Arguments']):
    icon = 'IconResources'
    description = 'Resource Types'
    children = [ 'ResTypeEdit', 'ResTypeDelete' ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):
        pass

    def checkAccess(self, user: IUser) -> None:
        checkPrivilege(user, 'rt/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield ResTypeTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
        return ResTypeTable.instance.present(proc=proc)

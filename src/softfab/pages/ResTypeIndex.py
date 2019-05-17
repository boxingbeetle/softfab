# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import (
    BoolDataColumn, DataColumn, DataTable, LinkColumn
)
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.restypelib import ResType, resTypeDB
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import XMLContent


class ResTypeLinkColumn(LinkColumn[ResType]):

    def presentCell(self, record: ResType, **kwargs: object) -> XMLContent:
        if record.getId().startswith('sf.'):
            return '-'
        else:
            return super().presentCell(record, **kwargs)

class ResTypeTable(DataTable[ResType]):
    db = resTypeDB
    columns = (
        DataColumn[ResType](keyName = 'presentationName', label = 'Name'),
        BoolDataColumn[ResType](keyName = 'pertask', label = 'Per Task'),
        BoolDataColumn[ResType](keyName = 'perjob', label = 'Per Job'),
        ResTypeLinkColumn('Edit', 'ResTypeEdit'),
        ResTypeLinkColumn('Delete', 'ResTypeDelete'),
        )

class ResTypeIndex_GET(FabPage['ResTypeIndex_GET.Processor',
                               'ResTypeIndex_GET.Arguments']):
    icon = 'IconResources'
    description = 'Resource Types'
    children = [ 'ResTypeEdit', 'ResTypeDelete' ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor['ResTypeIndex_GET.Arguments']):
        pass

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'rt/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield ResTypeTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
        return ResTypeTable.instance.present(proc=proc)

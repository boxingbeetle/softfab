# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import (
    BoolDataColumn, DataColumn, DataTable, LinkColumn
)
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.resourcelib import resourceDB
from softfab.restypelib import ResType, resTypeDB
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import XMLContent


class ResCountLinkColumn(LinkColumn[ResType]):
    keyName = 'count'
    cellStyle = 'rightalign'

    @staticmethod
    def getCount(record: ResType) -> int:
        return len(resourceDB.resourcesOfType(record.getId()))

    sortKey = getCount

    def __init__(self) -> None:
        super().__init__('#', 'Capabilities', idArg='restype')

    def presentCell(self, record: ResType, **kwargs: object) -> XMLContent:
        return self.presentLink(record, **kwargs)[
            self.getCount(record)
            ]

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
        ResCountLinkColumn(),
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

    def presentContent(self, **kwargs: object) -> XMLContent:
        return ResTypeTable.instance.present(**kwargs)

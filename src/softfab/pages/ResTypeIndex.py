# SPDX-License-Identifier: BSD-3-Clause

from functools import partial
from typing import Any, ClassVar, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.databaselib import Retriever
from softfab.datawidgets import (
    BoolDataColumn, DataColumn, DataTable, LinkColumn
)
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.resourcelib import ResourceDB
from softfab.restypelib import ResType, ResTypeDB
from softfab.users import User, checkPrivilege
from softfab.xmlgen import XMLContent


def numResourcesOfType(resourceDB: ResourceDB, resType: ResType) -> int:
    return len(resourceDB.resourcesOfType(resType.getId()))

class ResCountLinkColumn(LinkColumn[ResType]):
    keyName = 'count'
    cellStyle = 'rightalign'

    def __init__(self) -> None:
        super().__init__('#', 'Capabilities', idArg='restype')

    def getSortKey(self, proc: PageProcessor) -> Retriever[ResType, str]:
        assert isinstance(proc, ResTypeIndex_GET.Processor)
        return cast(Retriever[ResType, str],
                    partial(numResourcesOfType, proc.resourceDB))

    def presentCell(self, record: ResType, **kwargs: object) -> XMLContent:
        proc = kwargs['proc']
        assert isinstance(proc, ResTypeIndex_GET.Processor)
        return self.presentLink(record, **kwargs)[
            numResourcesOfType(proc.resourceDB, record)
            ]

class ResTypeLinkColumn(LinkColumn[ResType]):

    def presentCell(self, record: ResType, **kwargs: object) -> XMLContent:
        if record.getId().startswith('sf.'):
            return '-'
        else:
            return super().presentCell(record, **kwargs)

class ResTypeTable(DataTable[ResType]):
    dbName = 'resTypeDB'
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
        resTypeDB: ClassVar[ResTypeDB]
        resourceDB: ClassVar[ResourceDB]

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'rt/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Any]]:
        yield ResTypeTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        return ResTypeTable.instance.present(**kwargs)

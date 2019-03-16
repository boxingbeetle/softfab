# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import (
    BoolDataColumn, DataColumn, DataTable, LinkColumn
)
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.pagelinks import createProductDetailsLink
from softfab.productdeflib import productDefDB
from softfab.userlib import checkPrivilege
from softfab.webgui import docLink
from softfab.xmlgen import XMLContent, xhtml


class NameColumn(DataColumn):
    label = 'Product ID'
    keyName = 'id'
    def presentCell(self, record, **kwargs):
        return createProductDetailsLink(record.getId())

class TypeColumn(DataColumn):
    label = 'Type'
    keyName = 'type'
    @staticmethod
    def sortKey(record):
        return record['type'].name

class ProductDefTable(DataTable):
    db = productDefDB
    columns = (
        NameColumn.instance,
        TypeColumn.instance,
        BoolDataColumn('Local', 'local'),
        BoolDataColumn('Combined', 'combined'),
        LinkColumn('Edit', 'ProductEdit'),
        LinkColumn('Delete', 'ProductDelete'),
        )

class ProductIndex_GET(FabPage['ProductIndex_GET.Processor', 'ProductIndex_GET.Arguments']):
    icon = 'Product1'
    description = 'Products'
    children = [ 'ProductDetails', 'ProductEdit', 'ProductDelete' ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):
        pass

    def checkAccess(self, req):
        checkPrivilege(req.user, 'pd/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield ProductDefTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
        yield ProductDefTable.instance.present(proc=proc)
        yield xhtml.p[
            'For help about "Products", please read the following document: ',
            docLink('/introduction/execution-graph/')[
                'Products in the Execution Graph'
                ], '.'
            ]

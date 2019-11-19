# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import (
    BoolDataColumn, DataColumn, DataTable, LinkColumn
)
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.pagelinks import createProductDetailsLink
from softfab.productdeflib import ProductDef, productDefDB
from softfab.userlib import User, checkPrivilege
from softfab.webgui import docLink
from softfab.xmlgen import XMLContent, xhtml


class NameColumn(DataColumn[ProductDef]):
    label = 'Product ID'
    keyName = 'id'

    def presentCell(self, record: ProductDef, **kwargs: object) -> XMLContent:
        return createProductDetailsLink(record.getId())

class TypeColumn(DataColumn[ProductDef]):
    label = 'Type'
    keyName = 'type'

    @staticmethod
    def typeName(record: ProductDef) -> str:
        return record.getType().name

    sortKey = typeName

class ProductDefTable(DataTable[ProductDef]):
    db = productDefDB
    columns = (
        NameColumn.instance,
        TypeColumn.instance,
        BoolDataColumn[ProductDef]('Local', 'local'),
        BoolDataColumn[ProductDef]('Combined', 'combined'),
        LinkColumn[ProductDef]('Edit', 'ProductEdit'),
        LinkColumn[ProductDef]('Delete', 'ProductDelete'),
        )

class ProductIndex_GET(FabPage['ProductIndex_GET.Processor',
                               'ProductIndex_GET.Arguments']):
    icon = 'Product1'
    description = 'Products'
    children = [ 'ProductDetails', 'ProductEdit', 'ProductDelete' ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor['ProductIndex_GET.Arguments']):
        pass

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'pd/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield ProductDefTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield ProductDefTable.instance.present(**kwargs)
        yield xhtml.p[
            'For help about products, please read the following document: ',
            docLink('/concepts/exegraph/')[
                'Execution Graph'
                ], '.'
            ]

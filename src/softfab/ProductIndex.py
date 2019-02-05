# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from Page import PageProcessor
from datawidgets import BoolDataColumn, DataColumn, DataTable, LinkColumn
from pageargs import IntArg, PageArgs, SortArg
from pagelinks import createProductDetailsLink
from productdeflib import productDefDB
from webgui import docLink
from xmlgen import xhtml

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

class ProductIndex(FabPage):
    icon = 'Product1'
    description = 'Products'
    children = [ 'ProductDetails', 'ProductEdit', 'ProductDelete' ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):
        pass

    def checkAccess(self, req):
        req.checkPrivilege('pd/l')

    def iterDataTables(self, proc):
        yield ProductDefTable.instance

    def presentContent(self, proc):
        yield ProductDefTable.instance.present(proc=proc)
        yield xhtml.p[
            'For help about "Products", please read the following document: ',
            docLink('/concepts/execution_graph/')[
                'Products in the Execution Graph'
                ], '.'
            ]

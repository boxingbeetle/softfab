# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import (
    BoolDataColumn, DataColumn, DataTable, LinkColumn, ListDataColumn
)
from softfab.frameworklib import anyExtract, frameworkDB
from softfab.frameworkview import FrameworkColumn
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.pagelinks import createProductDetailsLink
from softfab.userlib import User, checkPrivilege
from softfab.webgui import docLink
from softfab.xmlgen import XMLContent, txt, xhtml


class ProductColumn(DataColumn):
    def presentCell(self, record, **kwargs):
        return txt(', ').join(
            createProductDetailsLink(productDefId)
            for productDefId in record[self.keyName]
            )

class FrameworksTable(DataTable):
    db = frameworkDB
    nameColumn = FrameworkColumn('Framework ID', 'id')
    wrapperColumn = DataColumn('Wrapper', 'wrapper')
    extractColumn = BoolDataColumn('Extract', 'extract')
    inputColumn = ProductColumn('Input Products', 'inputs')
    outputColumn = ProductColumn('Output Products', 'outputs')
    parameterColumn = ListDataColumn('Parameters', 'parameters')
    editColumn = LinkColumn('Edit', 'FrameworkEdit')
    deleteColumn = LinkColumn('Delete', 'FrameworkDelete')

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn]:
        yield self.nameColumn
        yield self.wrapperColumn
        if anyExtract():
            yield self.extractColumn
        yield self.inputColumn
        yield self.outputColumn
        yield self.parameterColumn
        yield self.editColumn
        yield self.deleteColumn

class FrameworkIndex_GET(FabPage['FrameworkIndex_GET.Processor',
                                 'FrameworkIndex_GET.Arguments']):
    icon = 'Framework1'
    description = 'Frameworks'
    children = [ 'FrameworkDetails', 'FrameworkEdit', 'FrameworkDelete' ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor['FrameworkIndex_GET.Arguments']):
        pass

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'fd/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield FrameworksTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
        yield FrameworksTable.instance.present(proc=proc)
        yield xhtml.p[
            'Final parameters are not shown in the table above. '
            'If you follow one of the framework name links, you are taken '
            'to the framework details page which lists all parameters.'
            ]
        yield xhtml.p[
            'For help about "Frameworks" or "Task Definitions" read the '
            'document: ',
            docLink('/introduction/framework-and-task-definitions/')[
                'Framework and Task Definitions'
                ], '.'
            ]

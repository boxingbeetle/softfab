# SPDX-License-Identifier: BSD-3-Clause

from typing import Any, ClassVar, Iterable, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import (
    DataColumn, DataTable, LinkColumn, ListDataColumn
)
from softfab.frameworklib import FrameworkDB, TaskDefBase
from softfab.frameworkview import FrameworkColumn
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.pagelinks import createProductDetailsLink
from softfab.users import User, checkPrivilege
from softfab.webgui import docLink
from softfab.xmlgen import XMLContent, xhtml


class ProductColumn(DataColumn[TaskDefBase]):
    def presentCell(self, record: TaskDefBase, **kwargs: object) -> XMLContent:
        keyName = self.keyName
        assert keyName is not None
        return xhtml[', '].join(
            createProductDetailsLink(productDefId)
            for productDefId in cast(Iterable[str], record[keyName])
            )

class FrameworksTable(DataTable[TaskDefBase]):
    dbName = 'frameworkDB'
    nameColumn = FrameworkColumn('Framework ID', 'id')
    wrapperColumn = DataColumn[TaskDefBase]('Wrapper', 'wrapper')
    inputColumn = ProductColumn('Input Products', 'inputs')
    outputColumn = ProductColumn('Output Products', 'outputs')
    parameterColumn = ListDataColumn[TaskDefBase]('Parameters', 'parameters')
    editColumn = LinkColumn[TaskDefBase]('Edit', 'FrameworkEdit')
    deleteColumn = LinkColumn[TaskDefBase]('Delete', 'FrameworkDelete')

    def iterColumns(self, # pylint: disable=unused-argument
                    **kwargs: object
                    ) -> Iterator[DataColumn[TaskDefBase]]:
        yield self.nameColumn
        yield self.wrapperColumn
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
        frameworkDB: ClassVar[FrameworkDB]

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'fd/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Any]]:
        yield FrameworksTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield FrameworksTable.instance.present(**kwargs)
        yield xhtml.p[
            'Final parameters are not shown in the table above. '
            'If you follow one of the framework name links, you are taken '
            'to the framework details page which lists all parameters.'
            ]
        yield xhtml.p[
            'For help about "Frameworks" or "Task Definitions" read the '
            'document: ',
            docLink('/concepts/taskdefs/')[
                'Framework and Task Definitions'
                ], '.'
            ]

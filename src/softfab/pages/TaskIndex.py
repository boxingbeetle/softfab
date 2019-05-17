# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import (
    DataColumn, DataTable, LinkColumn, ListDataColumn
)
from softfab.frameworkview import FrameworkColumn
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.pagelinks import createTaskDetailsLink
from softfab.taskdeflib import TaskDef, taskDefDB
from softfab.userlib import User, checkPrivilege
from softfab.webgui import docLink
from softfab.xmlgen import XMLContent, xhtml


class NameColumn(DataColumn[TaskDef]):
    label = 'Task Definition ID'
    keyName = 'id'
    def presentCell(self, record, **kwargs):
        return createTaskDetailsLink(record.getId())

class TasksTable(DataTable[TaskDef]):
    db = taskDefDB
    columns = (
        NameColumn.instance,
        DataColumn[TaskDef]('Title', 'title'),
        FrameworkColumn('Framework ID', 'parent'),
        ListDataColumn[TaskDef]('Parameters', 'parameters'),
        LinkColumn[TaskDef]('Edit', 'TaskEdit'),
        LinkColumn[TaskDef]('Delete', 'TaskDelete'),
        )

class TaskIndex_GET(FabPage['TaskIndex_GET.Processor',
                            'TaskIndex_GET.Arguments']):
    icon = 'TaskDef2'
    description = 'Task Definitions'
    children = [ 'TaskDetails', 'TaskEdit', 'TaskDelete']

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor['TaskIndex_GET.Arguments']):
        pass

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'td/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield TasksTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
        yield TasksTable.instance.present(proc=proc)
        yield xhtml.p[
            'Final parameters are not shown in the table above. '
            'If you follow one of the task definition name links, you are '
            'taken to the task definition details page which lists all '
            'parameters.'
            ]
        yield xhtml.p[
            'For help about "Frameworks" or "Task Definitions" read the '
            'document: ',
            docLink('/introduction/framework-and-task-definitions/')[
                'Framework and Task Definitions'
                ],
                '.'
            ]

# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import (
    DataColumn, DataTable, LinkColumn, ListDataColumn
    )
from softfab.frameworkview import FrameworkColumn
from softfab.pageargs import IntArg, PageArgs, SortArg
from softfab.pagelinks import createTaskDetailsLink
from softfab.taskdeflib import taskDefDB
from softfab.webgui import docLink
from softfab.xmlgen import xhtml

class NameColumn(DataColumn):
    label = 'Task Definition ID'
    keyName = 'id'
    def presentCell(self, record, **kwargs):
        return createTaskDetailsLink(record.getId())

class TasksTable(DataTable):
    db = taskDefDB
    columns = (
        NameColumn.instance,
        DataColumn('Title', 'title'),
        FrameworkColumn('Framework ID', 'parent'),
        ListDataColumn('Parameters', 'parameters'),
        LinkColumn('Edit', 'TaskEdit'),
        LinkColumn('Delete', 'TaskDelete'),
        )

class TaskIndex(FabPage):
    icon = 'TaskDef2'
    description = 'Task Definitions'
    children = [ 'TaskDetails', 'TaskEdit', 'TaskDelete']

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):
        pass

    def checkAccess(self, req):
        req.checkPrivilege('td/l')

    def iterDataTables(self, proc):
        yield TasksTable.instance

    def presentContent(self, proc):
        yield TasksTable.instance.present(proc=proc)
        yield xhtml.p[
            'Final parameters are not shown in the table above. '
            'If you follow one of the task definition name links, you are '
            'taken to the task definition details page which lists all '
            'parameters.'
            ]
        yield xhtml.p[
            'For help about "Frameworks" or "Task Definitions" read the '
            'document: ', docLink('/concepts/task_definitions/')[
                'Framework and Task Definitions' ], '.'
            ]

# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, cast

from softfab.CSVPage import presentCSVLink
from softfab.FabPage import FabPage
from softfab.ReportMixin import (
    ExecutionState, ReportFilterForm, ReportProcessor, ReportTaskArgs,
    ReportTaskCSVArgs
)
from softfab.datawidgets import DataTable
from softfab.formlib import selectionList
from softfab.joblib import (
    iterAllTasks, iterDoneTasks, iterFinishedTasks, iterUnfinishedTasks, jobDB
)
from softfab.pageargs import IntArg, SortArg
from softfab.resultlib import getKeys
from softfab.setcalc import intersection, union
from softfab.taskdeflib import taskDefDB
from softfab.tasktables import TaskRunsTable
from softfab.userlib import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import pageLink
from softfab.xmlgen import XMLContent, xhtml


class FilteredTaskRunsTable(TaskRunsTable):

    def showTargetColumn(self) -> bool:
        return super().showTargetColumn() or bool(jobDB.uniqueValues('target'))

    def getRecordsToQuery(self, proc):
        # Note: iterAllTasks() etc can efficiently handle an empty (nothing
        #       matches) filter, no need for a special case here.
        return {
            ExecutionState.ALL: iterAllTasks,
            ExecutionState.COMPLETED: iterDoneTasks,
            ExecutionState.FINISHED: iterFinishedTasks,
            ExecutionState.UNFINISHED: iterUnfinishedTasks,
            }[proc.args.execState](proc.args.task)

    def iterFilters(self, proc):
        return proc.iterFilters()

class FilterForm(ReportFilterForm):
    objectName = FilteredTaskRunsTable.objectName

    def presentCustomBox(self, proc, numListItems, **kwargs):
        yield xhtml.td(colspan = 4)[
            selectionList(
                name='task', selected=proc.args.task, size=numListItems
                )[ sorted(taskDefDB.keys()) ]
            ]

class ReportTasks_GET(FabPage['ReportTasks_GET.Processor', 'ReportTasks_GET.Arguments']):
    icon = 'IconReport'
    description = 'Task History'
    children = [ 'ExtractedData' ]

    class Arguments(ReportTaskArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(ReportProcessor):
        pass

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/a', 'view the task list')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield FilteredTaskRunsTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ReportTasks_GET.Processor, kwargs['proc'])
        taskFilter = proc.args.task

        yield FilterForm.instance.present(numListItems=10, **kwargs)

        if len(taskFilter) == 0:
            return

        keySets = [ getKeys(taskName) for taskName in taskFilter ]
        commonKeys = intersection(keySets)
        combinedKeys = union(keySets)

        if combinedKeys:
            # For at least one selected task mid-level data is available.
            if commonKeys:
                numCommonKeys = len(commonKeys)
                yield xhtml.p[
                    pageLink('ExtractedData', ReportTaskArgs.subset(proc.args))[
                        'Visualize mid-level data'
                        ],
                    f" ({numCommonKeys:d} {pluralize('key', numCommonKeys)})"
                    ]
            else:
                yield xhtml.p[
                    'The selected tasks have mid-level data, '
                    'but they have no keys in common.'
                    ]

        yield presentCSVLink(
            'ReportTasksCSV',
            ReportTaskCSVArgs(ReportTaskArgs.subset(proc.args))
            )

        yield FilteredTaskRunsTable.instance.present(**kwargs)

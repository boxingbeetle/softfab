# SPDX-License-Identifier: BSD-3-Clause

from typing import Any, ClassVar, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.ReportMixin import ReportFilterForm, ReportProcessor
from softfab.datawidgets import DataTable
from softfab.formlib import selectionList
from softfab.joblib import (
    Task, iterAllTasks, iterDoneTasks, iterFinishedTasks, iterUnfinishedTasks
)
from softfab.pageargs import IntArg, SortArg
from softfab.pagelinks import ExecutionState, ReportTaskArgs
from softfab.querylib import RecordFilter
from softfab.setcalc import intersection, union
from softfab.taskdeflib import TaskDefDB
from softfab.taskrunlib import getKeys
from softfab.tasktables import TaskRunsTable
from softfab.userlib import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import pageLink
from softfab.xmlgen import XMLContent, xhtml


class FilteredTaskRunsTable(TaskRunsTable):

    def showTargetColumn(self, **kwargs: object) -> bool:
        proc = cast(ReportTasks_GET.Processor, kwargs['proc'])
        return super().showTargetColumn(**kwargs) \
            or bool(proc.jobDB.uniqueValues('target'))

    def getRecordsToQuery(self, proc: PageProcessor) -> Iterator[Task]:
        args = cast(ReportTasks_GET.Processor, proc).args
        # Note: iterAllTasks() etc can efficiently handle an empty (nothing
        #       matches) filter, no need for a special case here.
        return {
            ExecutionState.ALL: iterAllTasks,
            ExecutionState.COMPLETED: iterDoneTasks,
            ExecutionState.FINISHED: iterFinishedTasks,
            ExecutionState.UNFINISHED: iterUnfinishedTasks,
            }[args.execState](args.task)

    def iterFilters(self, proc: PageProcessor) -> Iterator[RecordFilter]:
        return cast(ReportTasks_GET.Processor, proc).iterFilters()

class FilterForm(ReportFilterForm):
    objectName = FilteredTaskRunsTable.objectName

    def presentCustomBox(self, **kwargs: object) -> XMLContent:
        proc = cast(ReportTasks_GET.Processor, kwargs['proc'])
        numListItems = cast(int, kwargs['numListItems'])
        yield xhtml.td(colspan = 4)[
            selectionList(
                name='task', selected=proc.args.task, size=numListItems
                )[ sorted(proc.taskDefDB.keys()) ]
            ]

class ReportTasks_GET(FabPage['ReportTasks_GET.Processor',
                              'ReportTasks_GET.Arguments']):
    icon = 'IconReport'
    description = 'Task History'
    children = [ 'ExtractedData' ]

    class Arguments(ReportTaskArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(ReportProcessor[Arguments]):
        taskDefDB: ClassVar[TaskDefDB]

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/a', 'view the task list')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Any]]:
        yield FilteredTaskRunsTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ReportTasks_GET.Processor, kwargs['proc'])
        taskFilter = proc.args.task

        if len(proc.taskDefDB) == 0:
            yield xhtml.p[
                'No tasks have been defined yet.'
                ]
            yield xhtml.p[
                'Go to the ', pageLink('Design')['Design page'],
                ' to input your execution graph.'
                ]
            return

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

        yield FilteredTaskRunsTable.instance.present(**kwargs)

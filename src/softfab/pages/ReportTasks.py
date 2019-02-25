# SPDX-License-Identifier: BSD-3-Clause

from softfab.CSVPage import presentCSVLink
from softfab.FabPage import FabPage
from softfab.ReportMixin import (
    ExecutionState, ReportFilterForm, ReportProcessor, ReportTaskArgs,
    ReportTaskCSVArgs
    )
from softfab.formlib import selectionList
from softfab.joblib import (
    iterAllTasks, iterDoneTasks, iterFinishedTasks, iterUnfinishedTasks,
    jobDB
    )
from softfab.pageargs import IntArg, SortArg
from softfab.resultlib import getKeys
from softfab.setcalc import intersection, union
from softfab.taskdeflib import taskDefDB
from softfab.tasktables import TaskRunsTable
from softfab.webgui import pageLink
from softfab.xmlgen import xhtml

class FilteredTaskRunsTable(TaskRunsTable):

    def showTargetColumn(self):
        return super().showTargetColumn() \
            or len(jobDB.uniqueValues('target')) > 1

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

class ReportTasks_GET(FabPage):
    icon = 'IconReport'
    description = 'Task History'
    children = [ 'ExtractedData' ]

    class Arguments(ReportTaskArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(ReportProcessor):
        pass

    def checkAccess(self, req):
        req.checkPrivilege('j/a', 'view the task list')

    def iterDataTables(self, proc):
        yield FilteredTaskRunsTable.instance

    def presentContent(self, proc):
        taskFilter = proc.args.task

        yield FilterForm.instance.present(proc, numListItems=10)

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
                    ' (%d %s)' % (
                        numCommonKeys, 'key' if numCommonKeys == 1 else 'keys'
                        )
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

        yield FilteredTaskRunsTable.instance.present(proc=proc)

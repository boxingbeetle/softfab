# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from typing import (
    Collection, DefaultDict, Dict, Iterable, Iterator, List, Mapping, Sequence,
    Tuple, cast
)

from softfab.CSVPage import presentCSVLink
from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.ReportMixin import ReportProcessor
from softfab.datawidgets import DataColumn, DataTable
from softfab.formlib import CheckBoxesTable, RadioTable, makeForm, submitButton
from softfab.joblib import Task, iterDoneTasks
from softfab.jobview import CreateTimeColumn
from softfab.pageargs import EnumArg, IntArg, SetArg, SortArg
from softfab.pagelinks import (
    ExecutionState, ReportTaskArgs, ReportTaskCSVArgs, VisualizationType,
    createRunURL
)
from softfab.querylib import KeySorter, RecordProcessor, runQuery
from softfab.request import Request
from softfab.setcalc import intersection
from softfab.taskrunlib import getData, getKeys
from softfab.tasktables import TaskColumn, TaskRunsTable
from softfab.timeview import formatTime
from softfab.userlib import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import pageLink
from softfab.xmlgen import XMLContent, xhtml


def gatherData(taskFilter: Iterable[str],
               tasks: Iterable[Task],
               activeKeys: Iterable[str]
               ) -> Mapping[str, Mapping[str, str]]:
    taskRunIdsByName: Dict[str, List[str]] = {
        taskName: [] for taskName in taskFilter
        }
    for task in tasks:
        taskRunIdsByName[task.getName()].append(task.getLatestRun().getId())
    dataByRunId: DefaultDict[str, Dict[str, str]] = defaultdict(dict)
    for key in activeKeys:
        for taskName in taskFilter:
            for runId, valueStr in getData(taskName, taskRunIdsByName[taskName],
                                           key):
                dataByRunId[runId][key] = valueStr
    return dataByRunId

class KeysTable(CheckBoxesTable):
    name = 'key'
    columns = 'Keys to include',
    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[str, Sequence[XMLContent]]]:
        proc = cast(ExtractedData_GET.Processor, kwargs['proc'])
        for key in sorted(proc.keys):
            yield key, (key,)
    def getActive(self, **kwargs: object) -> Collection[str]:
        proc = cast(ExtractedData_GET.Processor, kwargs['proc'])
        return proc.activeKeys

class VisualizationTable(RadioTable):
    name = 'vistype'
    columns = ('Visualization', )
    def iterOptions(self, **kwargs: object) -> Iterator[Sequence[XMLContent]]:
        yield VisualizationType.CHART_BAR, 'Bar chart'
        yield VisualizationType.TABLE, 'Table'

def visualizeBarCharts(proc: 'ExtractedData_GET.Processor') -> XMLContent:
    tasks = proc.tasks
    activeKeys = proc.activeKeys
    dataByRunId = proc.dataByRunId
    if len(activeKeys) == 0:
        yield xhtml.p[ 'Please select one or more keys.' ]
        return
    for key in sorted(activeKeys):
        yield visualizeBarChart(key, tasks, dataByRunId)

def visualizeBarChart(key: str,
                      tasks: Iterable[Task],
                      dataByRunId: Mapping[str, Mapping[str, str]]
                      ) -> XMLContent:
    yield xhtml.h3[ f'Chart for {key}:' ]

    dataPoints = []
    for task in tasks:
        runId = task.getLatestRun().getId()
        value = None
        data = dataByRunId.get(runId)
        if data is not None:
            valueStr = data.get(key)
            if valueStr is not None:
                try:
                    value = int(valueStr)
                except ValueError:
                    pass # value remains None
        dataPoints.append(( task, value ))

    graphWidth = 600 # pixels
    graphHeight = 300 # pixels
    markDistance = 20 # pixels
    minBarWidth = 3 # pixels
    maxBarWidth = markDistance

    # Drop off oldest results if there are too many.
    maxBars = graphWidth // (minBarWidth + 1)
    if len(dataPoints) > maxBars:
        yield xhtml.p[xhtml.i[
            f'To fit the chart on the page, only the last {maxBars:d} '
            f'data points of {len(dataPoints):d} total could be displayed.'
            ]]
        dataPoints[ : -maxBars] = []

    # Calculate height.
    maxValue = max(
        (value for task, value in dataPoints if value is not None),
        default = None
        )
    if maxValue is None:
        yield xhtml.p[
            'None of the selected tasks have an integer value '
            'stored for this key.'
            ]
        return
    elif maxValue <= 0:
        # Avoid division by zero later; the value is arbitrary.
        maxValue = 10
    graphHeight -= graphHeight % markDistance
    numMarks = graphHeight // markDistance
    # markValue = maxValue // numMarks #(unused)

    # Calculate a nice round number for the value distance between
    # two marks.
    roundMarkValue = 1
    while roundMarkValue * numMarks < maxValue:
        roundMarkValue *= 10
    if (roundMarkValue // 5) * numMarks >= maxValue:
        roundMarkValue //= 5
    elif (roundMarkValue // 2) * numMarks >= maxValue:
        roundMarkValue //= 2
    maxValue = roundMarkValue * numMarks

    # Calculate width of bars.
    barWidth = min(maxBarWidth, graphWidth // len(dataPoints))
    graphWidth = barWidth * len(dataPoints)

    def generateBars() -> XMLContent:
        assert maxValue is not None # work around mypy issue 2608
        for task, value in dataPoints:
            run = task.getLatestRun()
            if value is None:
                valueDescription = 'no value'
                barClass = 'graphbarnoval'
                height = graphHeight
            else:
                valueDescription = str(value)
                barClass = 'graphbar'
                # We cannot plot negative values, so clip to 0.
                height = max(value, 0) * graphHeight // maxValue
            url = createRunURL(run, 'data')
            yield xhtml.td(
                title = '%s - %s' % (
                    formatTime(run.getJob().getCreateTime()), valueDescription
                    ),
                onclick = f"document.location='{url}'"
                )[
                xhtml.table(
                    class_ = barClass,
                    style = f'width: {barWidth:d}px; height: {height:d}px'
                    )[ xhtml.tbody[ xhtml.tr[ xhtml.td ] ] ]
                ]
        yield xhtml.td(class_ = 'raxis')[(
            ( str(mark * roundMarkValue), xhtml.br )
            for mark in range(numMarks, 0, -1)
            )]
    yield xhtml.table(
        class_ = 'graph', style = f'height: {graphHeight:d}px'
        )[ xhtml.tbody[ xhtml.tr[ generateBars() ] ] ]

class ExtractedDataColumn(DataColumn[Task]):

    def __init__(self, key: str):
        DataColumn.__init__(self, key, cellStyle = 'rightalign')
        self.__key = key

    def presentCell(self, record: Task, **kwargs: object) -> XMLContent:
        proc = cast(ExtractedData_GET.Processor, kwargs['proc'])
        runId = record.getLatestRun().getId()
        data = proc.dataByRunId.get(runId)
        return '-' if data is None else data.get(self.__key, '-')

class ExtractedDataTable(TaskRunsTable):

    def getRecordsToQuery(self, proc: PageProcessor) -> Collection[Task]:
        return cast(ExtractedData_GET.Processor, proc).tasks

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn[Task]]:
        proc = cast(ExtractedData_GET.Processor, kwargs['proc'])
        yield CreateTimeColumn[Task].instance
        yield TaskColumn.instance
        for key in sorted(proc.activeKeys):
            yield ExtractedDataColumn(key)

class ExtractedData_GET(FabPage['ExtractedData_GET.Processor',
                                'ExtractedData_GET.Arguments']):
    icon = 'Reports2'
    description = 'Extracted Data'

    class Arguments(ReportTaskArgs):
        # Override to make 'task' argument mandatory.
        # Intersection of empty sequence is undefined, so we must ensure
        # at least one task is selected.
        task = SetArg(allowEmpty=False)

        key = SetArg()
        vistype = EnumArg(VisualizationType, VisualizationType.CHART_BAR)
        sort = SortArg()
        first = IntArg(0)

    class Processor(ReportProcessor[Arguments]):

        def process(self,
                    req: Request['ExtractedData_GET.Arguments'],
                    user: User
                    ) -> None:
            super().process(req, user)

            taskNames = req.args.task

            # Determine keys that exist for all the given task names.
            # And clean up the list of active keys.
            keys = intersection(
                getKeys(taskName) for taskName in taskNames
                )
            # The empty task set is rejected at argument parsing,
            # so the intersection is always defined.
            assert keys is not None
            activeKeys = req.args.key & keys

            # Query DB.
            query: List[RecordProcessor[Task]] = list(self.iterFilters())
            query.append(KeySorter[Task].forCustom([ 'starttime' ]))
            tasks = runQuery(query, iterDoneTasks(taskNames))
            dataByRunId = gatherData(taskNames, tasks, activeKeys)

            # pylint: disable=attribute-defined-outside-init
            self.keys = keys
            self.activeKeys = activeKeys
            self.tasks = tasks
            self.dataByRunId = dataByRunId

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 't/a')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield ExtractedDataTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ExtractedData_GET.Processor, kwargs['proc'])
        parentArgs = ReportTaskArgs.subset(proc.args)

        yield xhtml.p[
            self.presentTaskFilter(parentArgs)
            ]
        yield xhtml.p[
            pageLink('ReportTasks', parentArgs)[
                'Change task filters'
                ]
            ]

        yield makeForm(formId='keys', method='get')[
            KeysTable.instance,
            VisualizationTable.instance,
            xhtml.p[ submitButton[ 'Apply' ] ],
            ].present(**kwargs)

        yield presentCSVLink(
            'ReportTasksCSV',
            ReportTaskCSVArgs(ReportTaskArgs.subset(proc.args))
            )

        if len(proc.tasks) == 0:
            yield xhtml.p[ 'No tasks match the given filters.' ]
        elif proc.args.vistype is VisualizationType.CHART_BAR:
            yield visualizeBarCharts(proc)
        elif proc.args.vistype is VisualizationType.TABLE:
            yield ExtractedDataTable.instance.present(**kwargs)

    def presentTaskFilter(self, args: ReportTaskArgs) -> XMLContent:
        yield 'Showing data from ',

        execState = args.execState
        if execState is not ExecutionState.ALL:
            yield xhtml.b[execState.name.lower()], ' '

        taskNames = args.task
        yield xhtml[', '].join(xhtml.b[name] for name in sorted(taskNames))
        yield ' tasks'

        owners = args.owner
        if owners:
            yield ' owned by '
            yield xhtml[', '].join(xhtml.b[name] for name in sorted(owners))

        targets = args.target
        if targets:
            yield ' for ', pluralize('target', len(targets)), ' '
            yield xhtml[', '].join(xhtml.b[name] for name in sorted(targets))

        ctabove = args.ctabove
        ctbelow = args.ctbelow
        if ctabove and ctbelow:
            yield (
                ' created between ', xhtml.b[formatTime(ctabove)],
                ' and ', xhtml.b[formatTime(ctbelow)]
                )
        elif ctabove:
            yield ' created after ', xhtml.b[formatTime(ctabove)]
        elif ctbelow:
            yield ' created before ', xhtml.b[formatTime(ctbelow)]

        yield '.'

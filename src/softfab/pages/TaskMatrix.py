# SPDX-License-Identifier: BSD-3-Clause

from softfab.CSVPage import presentCSVLink
from softfab.FabPage import FabPage
from softfab.ReportMixin import ReportTaskArgs
from softfab.TaskMatrixCommon import (
    TaskMatrixArgs, TaskMatrixCSVArgs, TaskMatrixProcessor, dateRange
    )
from softfab.configlib import configDB
from softfab.formlib import dropDownList, emptyOption, makeForm, submitButton
from softfab.jobview import createStatusBar
from softfab.timelib import normalizeWeek, secondsPerDay, weeksInYear, iterDays
from softfab.webgui import Table, cell, pageLink, pageURL
from softfab.xmlgen import XMLContent, xhtml

from collections import defaultdict
import time

def dateLink(args, year, week):
    return pageLink('TaskMatrix', args.override(year = year, week = week))

class NavigationBar(Table):
    '''A navigation bar where the user can select which week to display.
    '''
    columns = None, None, None, None

    def iterRows(self, *, proc, **kwargs):
        args = proc.args
        week = args.week
        year = args.year
        yield (
            cell[
                'Year: ',
                xhtml.span(class_ = 'nobreak')[
                    dateLink(args, year - 1, min(week, weeksInYear(year - 1)))[
                        '\u2190'
                        ],
                    dropDownList(name = 'year')[
                        range(dateRange.minYear, dateRange.maxYear + 1)
                        ].present(proc=proc, **kwargs),
                    dateLink(args, year + 1, min(week, weeksInYear(year + 1)))[
                        '\u2192'
                        ]
                    ]
                ],
            cell[
                'Week: ',
                xhtml.span(class_ = 'nobreak')[
                    dateLink(args, *normalizeWeek(year, week - 1))[ '\u2190' ],
                    dropDownList(name = 'week')[
                        range(1, weeksInYear(year) + 1)
                        ].present(proc=proc, **kwargs),
                    dateLink(args, *normalizeWeek(year, week + 1))[ '\u2192' ]
                    ]
                ],
            cell[
                'Configuration: ',
                dropDownList(name = 'config')[
                    emptyOption[ '(All - no filter)' ],
                    sorted(configDB.uniqueValues('name'))
                    ].present(proc=proc, **kwargs)
                ],
            cell[
                submitButton[ 'Apply' ].present(proc=proc, **kwargs)
                ]
            )

class Matrix(Table):
    '''Matrix table, with y-axis: all tasksdef names and x-axis: all "group"
    items. In each matrix cell the match between task and group is shown
    similar to the "status" cells on the ReportIndex page.
    By default the latest, not-deleted task definitions are show on the x-axis.
    Deleted task definitions are not visible unless a result should be
    displayed wich uses it.
    '''

    def iterColumns(self, proc, **kwargs):
        yield 'Task Definitions'
        dayStart = proc.beginWeek
        for _ in range(7):
            timestamp = time.localtime(dayStart)
            # Note: This would fail in the weeks in which daylight saving time
            #       starts or ends, except that we only print 1 week and the
            #       day on which the time adjustment is done is always Sunday.
            dayStart += secondsPerDay
            yield (
                time.strftime("%a", timestamp),
                xhtml.br,
                time.strftime("%d %b", timestamp),
                )
        yield 'Total'
        yield 'Week'

    def iterRows(self, *, proc, **kwargs):
        beginWeek = proc.beginWeek
        endWeek = proc.endWeek
        taskData = proc.taskData
        tasksByName = proc.tasksByName
        tasksByDay = proc.tasksByDay
        allTasks = proc.allTasks

        taskNames = set()
        # Add task names for task runs that were created in the selected week.
        taskNames.update(tasksByName)

        def makeURL(taskName, beginTime, endTime):
            if taskName is None:
                # TODO: The links which match all tasks are currently disabled,
                #       but are also no longer accepted by ReportTasks.
                taskName = '*'
            return pageURL(
                'ReportTasks',
                ReportTaskArgs(
                    task = [ taskName ], ctabove = beginTime, ctbelow = endTime
                    )
                )

        def createCell(taskName, tasks, beginTime, endTime):
            if tasks is None:
                return ''
            bar = createStatusBar(tasks, length = 0)
            if taskName is None:
                return bar
            url = makeURL(taskName, beginTime, endTime)
            return cell(onclick = "document.location='%s'" % url)[
                xhtml.a(href = url)[ bar ]
                ]

        def iterCells(taskName, rowHeader, weekTasks, totalTasks):
            # pylint: disable=stop-iteration-return
            # https://github.com/PyCQA/pylint/issues/2158

            yield rowHeader

            dayStartGen = iterDays(beginWeek)
            todayStart = next(dayStartGen)
            for tasks in weekTasks:
                tomorrowStart = next(dayStartGen)
                yield createCell(taskName, tasks, todayStart, tomorrowStart)
                todayStart = tomorrowStart

            yield cell(class_ = 'rightalign')[
                str(len(totalTasks)) if totalTasks else ''
                ]
            yield createCell(taskName, totalTasks, beginWeek, endWeek)

        if len(taskNames) == 0:
            yield iterCells(
                None,
                xhtml.i[ 'No Tasks' ],
                tasksByDay,
                allTasks
                )
        else:
            for taskName in sorted(taskNames):
                yield iterCells(
                    taskName,
                    xhtml.a(href = makeURL(taskName, beginWeek, endWeek))[
                        taskName
                        ],
                    ( taskDict.get(taskName) for taskDict in taskData ),
                    tasksByName.get(taskName)
                    )
        yield [ xhtml.b[ 'Total' ] ] + [
            cell(class_ = 'rightalign')[str(len(tasks)) if tasks else '']
            for tasks in tasksByDay
            ] + [ '', '' ]
        yield iterCells(
            None,
            xhtml.b[ 'All Tasks' ],
            tasksByDay,
            allTasks
            )

class TaskMatrix_GET(FabPage['TaskMatrix_GET.Processor']):
    icon = 'IconMatrix'
    description = 'Task Matrix'

    class Arguments(TaskMatrixArgs):
        pass

    class Processor(TaskMatrixProcessor):

        def process(self, req):
            # pylint: disable=attribute-defined-outside-init
            super().process(req)
            self.tasksByName = tasksByName = defaultdict(list)
            self.tasksByDay = tasksByDay = []
            self.allTasks = allTasks = []
            for dayTasks in self.taskData:
                combinedDayTasks = []
                for name, tasks in dayTasks.items():
                    combinedDayTasks.extend(tasks)
                    tasksByName[name].extend(tasks)
                tasksByDay.append(combinedDayTasks)
                allTasks.extend(combinedDayTasks)

    def checkAccess(self, req):
        req.checkPrivilege('j/a', 'view the task list')

    def presentContent(self, proc: Processor) -> XMLContent:
        yield makeForm(method = 'get', args = proc.args)[
            NavigationBar.instance
            ].present(proc=proc)
        yield presentCSVLink(
            'TaskMatrixCSV',
            TaskMatrixCSVArgs(proc.args)
            )
        yield Matrix.instance.present(proc=proc)

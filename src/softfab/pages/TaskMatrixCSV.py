# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Iterator, Mapping, Optional, Sequence, Set, cast
import time

from softfab.CSVPage import CSVPage
from softfab.TaskMatrixCommon import TaskMatrixCSVArgs, TaskMatrixProcessor
from softfab.joblib import Task
from softfab.querylib import KeySorter
from softfab.resultcode import ResultCode
from softfab.taskdeflib import TaskDefDB
from softfab.timelib import secondsPerDay
from softfab.userlib import User, checkPrivilege


class TaskMatrixCSV_GET(CSVPage['TaskMatrixCSV_GET.Processor']):

    class Arguments(TaskMatrixCSVArgs):
        pass

    class Processor(TaskMatrixProcessor):
        taskDefDB: ClassVar[TaskDefDB]

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/a', 'view the task list')

    def getFileName(self, proc: Processor) -> str:
        configFilter = proc.args.config
        return 'TaskMatrix_%d_%d%s.csv' % (
            cast(int, proc.args.year),
            cast(int, proc.args.week),
            '_' + configFilter if configFilter else ''
            )

    def iterRows(self, proc: Processor) -> Iterator[Sequence[str]]:
        # Get info from page arguments.
        year = proc.args.year
        week = proc.args.week
        configFilter = proc.args.config

        # Get info from processor.
        taskData = proc.taskData
        beginWeek = proc.beginWeek

        yield 'year', str(year)
        yield 'week', str(week)
        yield 'configuration', configFilter or 'all'
        yield ()

        if configFilter:
            taskNames: Set[str] = set()
        else:
            # Get list of names of current task definitions.
            taskNames = set(proc.taskDefDB.keys())
        # Add task names for task runs that were created in the selected
        # week.
        for taskDict in taskData:
            taskNames.update(taskDict)

        # Note: This would fail in the weeks in which daylight saving time
        #       starts or ends, except that we only print 1 week and the day
        #       on which the time adjustment is done is always Sunday.
        yield [ '' ] + [
            time.strftime(
                '%a %d %b',
                time.localtime(beginWeek + dayOfWeek * secondsPerDay)
                )
            for dayOfWeek in range(7)
            ]
        # Take the result of the most recent execution of each task, since that
        # is most likely to be representative.
        sorter: KeySorter[Task] = KeySorter.forCustom(['-starttime'])
        for taskName in sorted(taskNames):
            resultCells = [ taskName ]
            for taskDict in taskData:
                tasks = taskDict.get(taskName, ())
                for taskRun in sorter(tasks):
                    taskResult = RESULT_MAP.get(taskRun.result)
                    if taskResult is not None:
                        result = taskResult
                        break
                else:
                    result = 'X'
                resultCells.append(result)
            yield resultCells

RESULT_MAP: Mapping[Optional[ResultCode], str] = {
    ResultCode.OK: 'P',
    ResultCode.WARNING: 'F',
    ResultCode.ERROR: 'F'
}

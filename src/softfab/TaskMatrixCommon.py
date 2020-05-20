# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from time import localtime
from typing import ClassVar, DefaultDict, Iterable, List, Optional

from softfab.CSVPage import CSVPage
from softfab.Page import PageProcessor
from softfab.joblib import Job, JobDB, Task, dateRange
from softfab.pageargs import ArgsCorrected, IntArg, PageArgs, StrArg, dynamic
from softfab.querylib import CustomFilter, runQuery
from softfab.request import Request
from softfab.timelib import getWeekNr, secondsPerDay, weekRange, weeksInYear
from softfab.userlib import User


def filterJobs(jobs: Iterable[Job],
               beginWeek: int,
               endWeek: int,
               configFilter: Optional[str]
               ) -> List[Job]:
    '''Returns a new list containing those jobs from the given list
    which match the configuration and time filter.
    '''
    query = []

    if configFilter:
        def configMatches(job: Job) -> bool:
            return job.configId == configFilter
        query.append(CustomFilter(configMatches))

    def timeMatches(job: Job) -> bool:
        return beginWeek <= job.getCreateTime() < endWeek
    query.append(CustomFilter(timeMatches))

    return runQuery(query, jobs)

def groupTasks(jobs: Iterable[Job],
               beginWeek: int
               ) -> List[DefaultDict[str, List[Task]]]:
    '''Returns a list with 7 entries, one for each day of the week.
    Each entry is a dictionary with task name as key and a list of
    corresponding tasks as the value.
    '''
    taskData: List[DefaultDict[str, List[Task]]] = [
        defaultdict(list) for _ in range(7)
        ]
    # In the transition from summer time to winter time,
    # the week is 1 hour longer.
    # By assigning the 7th day dictionary to the 8th day,
    # tasks run in this extra hour are assigned to Sunday.
    # TODO: Is it OK to assume the extra hour is always on Sunday?
    taskData.append(taskData[6])
    for job in jobs:
        taskDict = taskData[(job.getCreateTime() - beginWeek) // secondsPerDay]
        for task in job.getTasks():
            taskDict[task.getName()].append(task)
    del taskData[7]
    return taskData

class TaskMatrixArgs(PageArgs):
    '''The filters used in the task matrix (HTML and CSV version).
    '''
    year = IntArg(dynamic)
    week = IntArg(dynamic)
    config = StrArg('')

class TaskMatrixCSVArgs(TaskMatrixArgs, CSVPage.Arguments):
    pass

class TaskMatrixProcessor(PageProcessor[TaskMatrixArgs]):

    jobDB: ClassVar[JobDB]

    async def process(self, req: Request[TaskMatrixArgs], user: User) -> None:
        # TODO: It would be useful to have these as method arguments.
        year = req.args.year
        week = req.args.week

        # Use week of last report as default.
        if year is dynamic or week is dynamic:
            year = dateRange.maxYear
            week = getWeekNr(localtime(dateRange.maxTime))
        else:
            assert isinstance(year, int)
            assert isinstance(week, int)

        # Bring date within a valid range.
        beginWeek, endWeek = weekRange(year, week)
        if beginWeek < dateRange.minTime:
            year = dateRange.minYear
            week = getWeekNr(localtime(dateRange.minTime))
        elif beginWeek > dateRange.maxTime:
            year = dateRange.maxYear
            week = getWeekNr(localtime(dateRange.maxTime))
        week = max(1, min(week, weeksInYear(year)))

        if year != req.args.year or week != req.args.week:
            # Redirect to the selected year and week.
            raise ArgsCorrected(req.args, year = year, week = week)

        # pylint: disable=attribute-defined-outside-init
        self.beginWeek = beginWeek
        self.endWeek = endWeek
        self.taskData = groupTasks(
            filterJobs(self.jobDB, beginWeek, endWeek, req.args.config),
            beginWeek
            )

# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from typing import DefaultDict, Iterable, List, Optional
import time

from softfab.CSVPage import CSVPage
from softfab.Page import PageProcessor
from softfab.databaselib import RecordObserver
from softfab.joblib import Job, Task, jobDB
from softfab.pageargs import ArgsCorrected, IntArg, PageArgs, StrArg, dynamic
from softfab.querylib import CustomFilter, runQuery
from softfab.request import Request
from softfab.timelib import (
    getTime, getWeekNr, secondsPerDay, weekRange, weeksInYear
)
from softfab.userlib import User


class DateRangeMonitor(RecordObserver[Job]):
    @property
    def minTime(self) -> int:
        return self.__minTime

    @property
    def maxTime(self) -> int:
        return self.__maxTime

    @property
    def minYear(self) -> int:
        return self.__minYear

    @property
    def maxYear(self) -> int:
        return self.__maxYear

    def __init__(self) -> None:
        RecordObserver.__init__(self)
        # Determine minimum and maximum job time.
        createTimes = [ job.getCreateTime() for job in jobDB ]
        if createTimes:
            self.__minTime = min(createTimes)
            self.__maxTime = max(createTimes)
        else:
            now = getTime()
            self.__minTime = now
            self.__maxTime = now
        self.__minYear = time.localtime(self.__minTime)[0]
        self.__maxYear = time.localtime(self.__maxTime)[0]

        # Register for updates.
        jobDB.addObserver(self)

    def added(self, record: Job) -> None:
        createTime = record.getCreateTime()
        self.__maxTime = createTime
        year = time.localtime(createTime)[0]
        if year > self.__maxYear:
            self.__maxYear = year

    def removed(self, record: Job) -> None:
        assert False, 'job was removed'

    def updated(self, record: Job) -> None:
        # Create time cannot change, so we don't care.
        pass

dateRange = DateRangeMonitor()

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
            return job.getConfigId() == configFilter
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
    taskData = [
        defaultdict(list) for _ in range(7)
        ] # type: List[DefaultDict[str, List[Task]]]
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

class TaskMatrixProcessor(PageProcessor[TaskMatrixCSVArgs]):

    def process(self, req: Request[TaskMatrixCSVArgs], user: User) -> None:
        # TODO: It would be useful to have these as method arguments.
        year = req.args.year
        week = req.args.week

        # Use week of last report as default.
        if year is dynamic or week is dynamic:
            year = dateRange.maxYear
            week = getWeekNr(time.localtime(dateRange.maxTime))
        else:
            assert isinstance(year, int)
            assert isinstance(week, int)

        # Bring date within a valid range.
        beginWeek, endWeek = weekRange(year, week)
        if beginWeek < dateRange.minTime:
            year = dateRange.minYear
            week = getWeekNr(time.localtime(dateRange.minTime))
        elif beginWeek > dateRange.maxTime:
            year = dateRange.maxYear
            week = getWeekNr(time.localtime(dateRange.maxTime))
        week = max(1, min(week, weeksInYear(year)))

        if year != req.args.year or week != req.args.week:
            # Redirect to the selected year and week.
            raise ArgsCorrected(req.args, year = year, week = week)

        # pylint: disable=attribute-defined-outside-init
        self.beginWeek = beginWeek
        self.endWeek = endWeek
        self.taskData = groupTasks(
            filterJobs(jobDB, beginWeek, endWeek, req.args.config),
            beginWeek
            )

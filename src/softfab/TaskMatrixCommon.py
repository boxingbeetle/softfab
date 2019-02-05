# SPDX-License-Identifier: BSD-3-Clause

from CSVPage import CSVPage
from Page import PageProcessor
from databaselib import RecordObserver
from joblib import jobDB
from pageargs import ArgsCorrected, IntArg, PageArgs, StrArg, dynamic
from querylib import CustomFilter, runQuery
from timelib import getTime, getWeekNr, secondsPerDay, weekRange, weeksInYear

from collections import defaultdict
import time

class DateRangeMonitor(RecordObserver):
    minTime = property(lambda self: self.__minTime)
    maxTime = property(lambda self: self.__maxTime)
    minYear = property(lambda self: self.__minYear)
    maxYear = property(lambda self: self.__maxYear)

    def __init__(self):
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

    def added(self, record):
        createTime = record.getCreateTime()
        self.__maxTime = createTime
        year = time.localtime(createTime)[0]
        if year > self.__maxYear:
            self.__maxYear = year

    def removed(self, record):
        assert False, 'job was removed'

    def updated(self, record):
        # Create time cannot change, so we don't care.
        pass

dateRange = DateRangeMonitor()

def filterJobs(jobs, beginWeek, endWeek, configFilter):
    '''Returns a new list containing those jobs from the given list
    which match the configuration and time filter.
    '''
    query = []
    if configFilter:
        query.append(CustomFilter(
            lambda job: job.getConfigId() == configFilter
            ))
    query.append(CustomFilter(
        lambda job: beginWeek <= job.getCreateTime() < endWeek
        ))
    return runQuery(query, jobs)

def groupTasks(jobs, beginWeek):
    '''Returns a list with 7 entries, one for each day of the week.
    Each entry is a dictionary with task name as key and a list of
    corresponding tasks as the value.
    '''
    taskData = [ defaultdict(list) for _ in range(7) ]
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

class TaskMatrixProcessor(PageProcessor):

    def process(self, req):
        # TODO: It would be useful to have these as method arguments.
        year = req.args.year
        week = req.args.week

        # Use week of last report as default.
        if year is dynamic or week is dynamic:
            year = dateRange.maxYear
            week = getWeekNr(time.localtime(dateRange.maxTime))

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

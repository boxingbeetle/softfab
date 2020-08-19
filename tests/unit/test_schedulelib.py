# SPDX-License-Identifier: BSD-3-Clause

from pytest import fixture, mark

from datageneratorlib import DataGenerator

from softfab.resultcode import ResultCode
from softfab.schedulelib import ScheduleManager, ScheduleRepeat
from softfab.scheduleview import getScheduleStatus
from softfab.timelib import endOfTime, secondsPerDay, setTimeFunc
from softfab.timeview import formatTime

import time
from heapq import heappush, heappop


class DummyReactor:
    """Dummy replacement for Twisted's reactor.

    We don't need the callbacks to happen because we call
    ScheduleManager.trigger() manually.
    """
    def callLater(self, delay, func, *args, **kw):
        pass

secondsPerWeek = 7 * secondsPerDay

def sharedConfigFactory(configId):
    """Implements "configFactory" as passed to createSchedule() by returning
    the given config ID. This is useful if a single configuration is shared by
    multiple schedules.
    """
    return lambda: {'configId': configId}

class Simulator:
    """Runs a simulation of schedules in action.

    You should organise your test code like this:
    ( set expectations ; perform checks ; pass time )*
    While time passes, state is checked after every time increment,
    except the last one (when the end time is reached).
    """

    preparedTime = 6000 # multiple of 60: at a minute boundary
    """Time stamp used by the "prepare" method."""

    continuousDelay = 300 # multiple of 60: at a minute boundary
    """Minimum delay between two jobs created from the same continuous
    schedule.
    """

    duration = 2 * continuousDelay
    """Time a task takes to execute."""

    def __init__(self, databases, preparedTime=None):
        self.databases = databases
        if preparedTime is not None:
            self.preparedTime = preparedTime

        # Create singleton instance.
        self.scheduleManager = ScheduleManager(databases.configDB,
                                               databases.jobDB,
                                               databases.scheduleDB,
                                               DummyReactor())

        self.__taskRunnerAvailableCallbacks = []
        self.__timedCallbacks = []

        # Note: This must happen before the Task Runners are generated,
        #       otherwise their initial sync time is not valid.
        #       It must also happen before the job observer is registered,
        #       because that will check the current time.
        self.__currentTime = self.preparedTime
        setTimeFunc(self.getTime)

        self.jobs = []
        databases.jobDB.addObserver(self)

        class CustomGenerator(DataGenerator):
            numTasks = 1
            numInputs = [ 0 ]
            numOutputs = [ 0 ]

        self.dataGenerator = gen = CustomGenerator(databases)
        gen.createDefinitions()

        gen.createTaskRunners()
        trRecord = databases.resourceDB.get(gen.taskRunners[0])
        # Keep the TaskRunner alive for all runs we want to execute.
        trRecord.getWarnTimeout = lambda: endOfTime - 300
        trRecord.getLostTimeout = lambda: endOfTime - 60
        self.taskRunner = trRecord

        self.__isDone = False
        self.__nrCreatedJobs = 0
        self.__nrFinishedJobs = 0

        # Different per test case, so defined by prepare():
        self.scheduled = None
        self.__missingConfig = None
        self.__suspended = None

    def __performCallbacks(self):
        # Task Runner available callbacks.
        while self.__taskRunnerAvailableCallbacks \
        and not self.taskRunner.isReserved():
            self.__taskRunnerAvailableCallbacks.pop(0)()
        # Timed callbacks.
        while self.__timedCallbacks \
        and self.__timedCallbacks[0][0] <= self.__currentTime:
            callback = heappop(self.__timedCallbacks)[-1]
            callback()

    def __callAt(self, timestamp, handler):
        assert self.__currentTime <= timestamp, (
            'test code tries to register handler in the past'
            )
        heappush(self.__timedCallbacks, (timestamp, id(handler), handler))

    def __assignTask(self, job):
        task = job.assignTask(self.taskRunner)
        self.__callAt(
            self.__currentTime + self.duration,
            lambda: self.__taskDone(job, task.getName())
            )

    def __taskDone(self, job, taskName):
        job.taskDone(taskName, ResultCode.OK, 'Summary text', (), {})

    def added(self, job):
        assert job['timestamp'] == self.__currentTime
        self.jobs.append(job)
        self.__taskRunnerAvailableCallbacks.append(
            lambda: self.__assignTask(job)
            )

    def updated(self, job):
        pass

    def removed(self, job):
        assert False, job.getId()

    def createConfig(self):
        """Create a job configuration."""

        return self.dataGenerator.createConfiguration()

    def defaultConfigFactory(self):
        """Default implementation of "configFactory" as used by
        createSchedule(). It calls createConfig() to create a single config.
        """

        config = self.createConfig()
        assert len(self.databases.configDB) == 1
        return { 'configId': config.getId() }

    def createSchedule(
        self, scheduleId, suspended, startTime, sequence,
        owner = 'test_user', days = None, comment = 'this is a comment',
        configFactory = None
        ):
        if configFactory is None:
            configFactory = self.defaultConfigFactory
        extra = {
            'minDelay': self.continuousDelay // 60
            }
        if days is not None:
            extra['days'] = days
        extra.update(configFactory())
        element = self.databases.scheduleDB.create(
            scheduleId, suspended, startTime, sequence, owner, comment, extra
            )
        self.databases.scheduleDB.add(element)
        return element

    def expectedStatus(self):
        # TODO: Add tests that check handling of status "error".
        if self.__nrCreatedJobs > self.__nrFinishedJobs:
            return 'running'
        elif self.__isDone:
            return 'done'
        elif self.__missingConfig \
                or not self.scheduled.getMatchingConfigIds(self.databases.configDB):
            return 'warning'
        elif self.__suspended:
            return 'suspended'
        else:
            return 'ok'

    def checkStatus(self):
        schedule = self.scheduled
        if schedule is None:
            return
        assert schedule.isRunning() == (self.__nrCreatedJobs > self.__nrFinishedJobs)
        assert schedule.isDone() == self.__isDone
        if self.__missingConfig:
            assert len(schedule.getMatchingConfigIds(self.databases.configDB)) == 0
        assert schedule.isSuspended() == self.__suspended
        assert getScheduleStatus(self.databases.configDB, schedule) == self.expectedStatus()
        assert len(self.databases.jobDB) == self.__nrCreatedJobs
        finishedJobs = [
            job for job in self.databases.jobDB if job.isExecutionFinished()
            ]
        assert len(finishedJobs) == self.__nrFinishedJobs

    def getTime(self):
        return self.__currentTime

    def advanceTo(self, newTime, check=None):
        if check is None:
            check = self.checkStatus

        assert self.__currentTime <= newTime, (
            'test code tries to go back in time: from %d to %d'
            % ( self.__currentTime, newTime )
            )
        assert self.__currentTime % 60 == 0
        assert newTime % 60 == 0
        self.scheduleManager.trigger()
        self.__performCallbacks()
        while self.__currentTime < newTime:
            check()
            #print 'time %d -> %d' % ( self.getTime(), self.getTime() + 30 )
            # Events always happen on minute boundaries, so by using half-minute
            # steps we ensure that we always check the state in between two
            # events that do not occur simultaneously.
            self.__currentTime += 30
            self.scheduleManager.trigger()
            self.__performCallbacks()

    def wait(self, seconds, check=None):
        self.advanceTo(self.__currentTime + seconds, check)

    def setSuspend(self, suspended):
        self.__suspended = suspended
        self.scheduled.setSuspend(suspended)

    def prepare(
        self, deltaTime, sequence,
        days = None, missingConfig = False, suspended = False,
        configFactory = None
        ):
        # Store our view of the schedule state.
        self.__missingConfig = missingConfig
        self.__suspended = suspended

        # Create schedule.
        assert len(self.databases.scheduleDB) == 0
        schedId = 'schedule-name'
        if configFactory is None and missingConfig:
            configFactory = sharedConfigFactory('nonExisting')
        element = self.createSchedule(
            schedId, suspended, self.preparedTime + deltaTime,
            sequence, days = days, configFactory = configFactory
            )
        self.scheduled = scheduled = self.databases.scheduleDB.get(schedId)
        assert element is scheduled, (element, scheduled)

        # Verify initial status.
        self.checkStatus()

    def expectRunning(self, numJobs=1):
        self.__nrCreatedJobs += numJobs

    def expectJobDone(self):
        self.__nrFinishedJobs += 1

    def expectScheduleDone(self):
        self.__isDone = True

@fixture
def sim(request, databases):
    preparedTime = getattr(request, 'param', None)
    return Simulator(databases, preparedTime)

time2007 = mark.parametrize('sim',
                            [int(time.mktime((2007, 1, 1, 0, 0, 0, 0, 1, 0)))],
                            indirect=True)
"""Start Monday 2007-01-01 at midnight."""

def testScheduleNonExistingOnce(sim):
    """Test one-shot schedule with a non-existing config."""

    sim.prepare(-120, ScheduleRepeat.ONCE, missingConfig=True)
    sim.expectScheduleDone()
    sim.wait(60)

def testScheduleNonExistingRepeat(sim):
    """Test daily schedule with a non-existing config."""

    sim.prepare(-120, ScheduleRepeat.DAILY, missingConfig=True)
    sim.wait(60)

def testScheduleNonExistingSuspended(sim):
    """Test one-shot schedule with a non-existing config, which is suspended."""

    sim.prepare(-120, ScheduleRepeat.ONCE, missingConfig=True, suspended=True)
    sim.wait(60)

def testScheduleOnceSuspended(sim):
    """Test one-shot schedule which is suspended."""

    sim.prepare(-120, ScheduleRepeat.ONCE, suspended=True)
    sim.wait(60)

def testScheduleOnceFuture(sim):
    """Test one-shot schedule with a start time in the future."""

    sim.prepare(120, ScheduleRepeat.ONCE)
    sim.wait(60)

def testScheduleOncePast(sim):
    """Test one-shot schedule with a start time in the past."""

    sim.prepare(-120, ScheduleRepeat.ONCE)
    sim.expectScheduleDone()
    sim.expectRunning()
    sim.wait(60)
    assert sim.scheduled.lastRunTime == sim.preparedTime

def testScheduleOnceStart(sim):
    """Test that a one-shot schedule is started at the specified time."""

    startOffset = 120
    sim.prepare(startOffset, ScheduleRepeat.ONCE)
    sim.wait(startOffset)
    sim.expectRunning()
    sim.expectScheduleDone()
    sim.wait(60)
    assert sim.scheduled.lastRunTime == sim.preparedTime + startOffset

def testScheduleContinuousStart(sim):
    """'Test that a continuous schedule is started repeatedly."""

    startOffset = 120
    sim.prepare(startOffset, sequence=ScheduleRepeat.CONTINUOUSLY)
    sim.wait(startOffset)
    for loop_ in range(4):
        sim.expectRunning()
        sim.wait(sim.duration)
        sim.expectJobDone()

@mark.parametrize('startOffset', (120, 0))
def testScheduleContinuousDelay(sim, startOffset):
    """Test minimum delay between jobs started by continuous schedule.
    We test startOffset 0 because we once had a bug that only occurred
    when start time is ASAP.
    """

    sim.duration = 120
    sim.prepare(startOffset, sequence=ScheduleRepeat.CONTINUOUSLY)
    sim.wait(startOffset)
    for loop_ in range(4):
        sim.expectRunning()
        sim.wait(sim.duration)
        sim.expectJobDone()
        sim.wait(sim.continuousDelay - sim.duration)

def testScheduleContinuousSuspend(sim):
    """Test suspending a continous schedule."""

    startOffset = 120
    sim.prepare(startOffset, sequence=ScheduleRepeat.CONTINUOUSLY)
    sim.wait(startOffset)
    for loop_ in range(4):
        sim.expectRunning()
        sim.wait(60)
        sim.setSuspend(True)
        sim.wait(sim.duration - 60)
        sim.expectJobDone()
        sim.wait(60)
        sim.setSuspend(False)

def testScheduleContinuousDelete(sim):
    """Test deletion of a continous schedule during execution."""

    # Let the schedule run for a while.
    testScheduleContinuousDelay(sim, 120)

    # Delete schedule.
    sim.expectRunning()
    sim.wait(60)
    sim.databases.scheduleDB.remove(sim.scheduled)
    sim.scheduled = None
    assert len(sim.databases.scheduleDB) == 0
    sim.wait(sim.duration - 60)
    sim.expectJobDone()

    # Run for another day, no jobs should be created anymore.
    assert len(sim.databases.jobDB) == 5
    sim.wait(secondsPerDay)
    assert len(sim.databases.jobDB) == 5

@time2007
def testScheduleDailyStart(sim):
    """Test daily schedule."""

    # Schedule starts Monday 2007-01-01 at 13:01.
    startTime = int(time.mktime((2007, 1, 1, 13, 1, 0, 0, 0, 0)))
    sim.prepare(startTime - sim.preparedTime, sequence=ScheduleRepeat.DAILY)
    assert getScheduleStatus(sim.databases.configDB, sim.scheduled) == 'ok'

    # Run simulation for 1 week.
    # No checks are done during the simulation.
    sim.wait(secondsPerWeek, check=lambda: None)

    # Validate the results.
    creationTimes = [job['timestamp'] for job in sim.jobs]
    assert len(creationTimes) == 7
    for i in range(6):
        assert creationTimes[i + 1] - creationTimes[i] == secondsPerDay, \
            'There are not 24*60*60 seconds between two job runs'

@time2007
def testScheduleDailyOverflow(sim):
    """Test what happens if a job started from a daily schedule runs for
    longer than a day.
    """

    # Each job takes 40 hours to execute.
    sim.duration = 40 * 60 * 60

    # For non-continuous schedules, it does not matter whether the job
    # has finished executing, so this schenario should behave the same
    # as the previous one.
    testScheduleDailyStart(sim)

@time2007
def testScheduleWeeklyStart(sim):
    """Test weekly schedules with one day each."""

    configId = sim.createConfig().getId()

    # Create 7 schedules: one for each day of the week with a different
    # start time.
    scheduledTimes = []
    for day in range(7):
        # Schedule starts Monday 2007-01-01 at 13:01,
        # Tuesday 2007-01-02 at 13:03 etc.
        startTime = int(time.mktime(
            ( 2007, 1, 1 + day, 13, 1 + day * 2, 0, 0, 1, 0 )
            ))
        scheduledTimes.append(startTime)
        schedId = 'WeeklyStart_%d' % day
        sim.createSchedule(
            schedId, False, startTime,
            ScheduleRepeat.WEEKLY, days = '0' * day + '1' + '0' * (6 - day),
            configFactory=sharedConfigFactory(configId)
            )
        scheduled = sim.databases.scheduleDB.get(schedId)
        assert getScheduleStatus(sim.databases.configDB, scheduled) == 'ok'

    # Run simulation for 2 weeks.
    sim.wait(2 * secondsPerWeek, check=lambda: None)

    # Validate the results.
    assert set(sim.databases.jobDB) == set(sim.jobs)
    creationTimes = [job['timestamp'] for job in sim.jobs]
    assert len(creationTimes) == 14
    assert len(scheduledTimes) == 7
    for day in range(7):
        assert creationTimes[day] == scheduledTimes[day], \
            'Job did not start at scheduled time'
        assert creationTimes[7 + day] - creationTimes[day] == secondsPerWeek, \
            'There is not exactly 1 week between two job runs'

@time2007
def testScheduleWeeklyStartMultiDay(sim):
    """Test weekly schedules with multiple days."""

    configId = sim.createConfig().getId()

    # Create 2 schedules: Mon/Wed/Fri/Sun and Tue/Thu/Sat.
    scheduledTimes = []
    for i, dayString in enumerate(('1010101', '0101010')):
        startTime = int(time.mktime(
            ( 2007, 1, 1 + i, 13, 1 + i * 2, 0, 0, 1, 0 )
            ))
        scheduledTimes.append(startTime)
        schedId = 'WeeklyStartMultiDay_%d' % i
        sim.createSchedule(
            schedId, False, startTime, ScheduleRepeat.WEEKLY, days=dayString,
            configFactory=sharedConfigFactory(configId)
            )
        scheduled = sim.databases.scheduleDB.get(schedId)
        assert getScheduleStatus(sim.databases.configDB, scheduled) == 'ok'

    # Run simulation for 2 weeks.
    sim.wait(2 * secondsPerWeek, check=lambda: None)

    # Validate the results.
    assert set(sim.databases.jobDB) == set(sim.jobs)
    creationTimes = [job['timestamp'] for job in sim.jobs]
    assert len(creationTimes) == 14
    assert len(scheduledTimes) == 2
    for i in range(2):
        assert creationTimes[i] == scheduledTimes[i], \
            'Job did not start at scheduled time'
    for day in range(7):
        assert creationTimes[7 + day] - creationTimes[day] == secondsPerWeek, \
            'There is not exactly 1 week between two job runs'

@time2007
def testScheduleWeeklyStartCorrection(sim):
    """Test weekly schedule for which the start time should be corrected
    to the next available selected day.
    """

    configId = sim.createConfig().getId()

    def timeOnDay(day):
        return int(time.mktime(
            ( 2007, 1, day, 13, 0, 0, 0, 1, 0 )
            ))
    # Create 3 schedules always for Wednesday:
    # 1st is dated 2007-01-01, should be corrected to 2007-01-03
    # 2nd is dated 2007-01-03, should not changed
    # 3rd is dated 2007-01-05, should be corrected to 2007-01-10
    scheduledTimes = []
    for scheduledDay, correctedDay in ( 1, 3 ), ( 3, 3 ), ( 5, 10 ):
        startTime = timeOnDay(scheduledDay)
        schedId = 'WeeklyStartCorrection_%d' % scheduledDay
        scheduledTimes.append(
            ( schedId, startTime, timeOnDay(correctedDay) )
            )
        sim.createSchedule(
            schedId, False, startTime, ScheduleRepeat.WEEKLY, days='0010000',
            configFactory=sharedConfigFactory(configId)
            )
        scheduled = sim.databases.scheduleDB.get(schedId)
        assert getScheduleStatus(sim.databases.configDB, scheduled) == 'ok'

    # Run simulation for 4 weeks.
    sim.wait(4 * secondsPerWeek, check=lambda: None)

    # Validate the results.
    assert set(sim.databases.jobDB) == set(sim.jobs)
    for schedId, scheduledTime, correctedTime in scheduledTimes:
        jobsFromSchedule = [
            job for job in sim.jobs if job.getScheduledBy() == schedId
            ]
        assert 3 <= len(jobsFromSchedule) <= 4, jobsFromSchedule
        prevCreationTime = None
        for job in jobsFromSchedule:
            creationTime = job['timestamp']
            if prevCreationTime is None:
                assert scheduledTime <= creationTime, '%s > %s' % \
                    ( formatTime(scheduledTime), formatTime(creationTime) )
                assert creationTime == correctedTime, '%s != %s' % \
                    ( formatTime(creationTime), formatTime(correctedTime) )
            else:
                assert creationTime - prevCreationTime == secondsPerWeek, \
                    'There is not exactly 1 week between two job runs'
            prevCreationTime = creationTime

class TaggedConfigFactory:

    tagKey = 'keymaster'
    tagValue = 'gatekeeper'

    def __init__(self, dataGenerator, numConfigs):
        self.configs = [
            dataGenerator.createConfiguration(name = 'config%d' % count)
            for count in range(numConfigs)
            ]
        # Note that we don't need a TagCache for these tests.

    def __call__(self):
        return { 'tagKey': self.tagKey, 'tagValue': self.tagValue }

    def setTags(self):
        for config in self.configs:
            config.tags.setTag(self.tagKey, (self.tagValue, ))

def testScheduleTaggedNonMatching(sim):
    """Test firing a schedule with a tag that does not match any configs."""

    def configFactory():
        return { 'tagKey': 'nosuchkey', 'tagValue': 'dummy' }
    startOffset = 120
    sim.prepare(startOffset, ScheduleRepeat.ONCE, configFactory=configFactory)
    assert len(sim.scheduled.getMatchingConfigIds(sim.databases.configDB)) == 0
    sim.wait(startOffset)
    sim.expectScheduleDone()
    sim.wait(60)
    assert sim.scheduled.lastRunTime == sim.preparedTime + startOffset

def prepareTaggedStart(sim, sequence, numConfigs):
    configFactory = TaggedConfigFactory(sim.dataGenerator, numConfigs)
    startOffset = 120

    # Preparation.
    sim.prepare(startOffset, sequence, configFactory=configFactory)
    sim.startTime = sim.preparedTime + startOffset

    # Apply tag.
    assert len(sim.scheduled.getMatchingConfigIds(sim.databases.configDB)) == 0
    configFactory.setTags()
    assert len(sim.scheduled.getMatchingConfigIds(sim.databases.configDB)) == numConfigs

    # Execution.
    sim.wait(startOffset)

    return configFactory.configs

@mark.parametrize('numConfigs', (1, 2))
def testScheduleTaggedOnce(sim, numConfigs):
    """Test firing a schedule with a tag that matches one or more configs."""

    configs = prepareTaggedStart(sim, ScheduleRepeat.ONCE, numConfigs)
    sim.expectRunning(numJobs = numConfigs)
    sim.expectScheduleDone()
    sim.wait(60)
    assert sim.scheduled.lastRunTime == sim.startTime

    # Verify last started jobs.
    createdConfigs = {config.getId() for config in configs}
    jobDB = sim.databases.jobDB
    jobConfigs = {jobDB[jobId].configId for jobId in sim.scheduled.getLastJobs()}
    assert createdConfigs == jobConfigs

def testScheduleTaggedContinuous(sim):
    """Test repeating of continuous schedule which matches multiple configs."""

    numConfigs = 2
    prepareTaggedStart(sim, ScheduleRepeat.CONTINUOUSLY, numConfigs)
    for loop_ in range(4):
        sim.expectRunning(numJobs=numConfigs)
        sim.wait(sim.duration)
        sim.expectJobDone()
        sim.wait(sim.duration)
        sim.expectJobDone()

def testScheduleTaggedContinuousDelay(sim):
    """Test minimum delay of continuous schedule based on tag."""

    sim.duration = 120
    numConfigs = 2
    prepareTaggedStart(sim, ScheduleRepeat.CONTINUOUSLY, numConfigs)
    for loop_ in range(4):
        sim.expectRunning(numJobs=numConfigs)
        sim.wait(sim.duration)
        sim.expectJobDone()
        sim.wait(sim.duration)
        sim.expectJobDone()
        sim.wait(sim.continuousDelay - sim.duration * 2)

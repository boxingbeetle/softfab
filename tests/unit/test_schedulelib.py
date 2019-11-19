# SPDX-License-Identifier: BSD-3-Clause

from initconfig import config as cfg

from datageneratorlib import removeRec, DataGenerator

from softfab import (
    databases, configlib, joblib, resourcelib, schedulelib, scheduleview
    )
from softfab.projectlib import project
from softfab.resultcode import ResultCode
from softfab.scheduleview import getScheduleStatus
from softfab.timelib import endOfTime, secondsPerDay, setTimeFunc
from softfab.timeview import formatTime

import time, unittest
from heapq import heappush, heappop

class DummyReactor:
    '''Dummy replacement for Twisted's reactor.
    '''
    def callLater(self, delay, func, *args, **kw):
        pass

secondsPerWeek = 7 * secondsPerDay

def sharedConfigFactory(configId):
    '''Implements "configFactory" as passed to createSchedule() by returning
    the given config ID. This is useful if a single configuration is shared by
    multiple schedules.
    '''
    return lambda: { 'configId': configId }

class ScheduleFixtureMixin:
    '''Base class which defines an environment for the test cases to use.
    Runs a simulation of schedules in action.

    You should organise your test code like this:
    ( set expectations ; perform checks ; pass time )*
    While time passes, state is checked after every time increment,
    except the last one (when the end time is reached).
    '''

    # Time stamp used by the "prepare" method.
    preparedTime = 6000 # multiple of 60: at a minute boundary

    # Minimum delay between two jobs created from the same continuous schedule.
    continuousDelay = 300 # multiple of 60: at a minute boundary

    # Time a task takes to execute.
    duration = 2 * continuousDelay

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
        self.assertEqual(job['timestamp'], self.__currentTime)
        self.jobs.append(job)
        self.__taskRunnerAvailableCallbacks.append(
            lambda: self.__assignTask(job)
            )

    def updated(self, job):
        pass

    def removed(self, job):
        assert False, job.getId()

    def setUp(self):
        self.reloadDatabases()
        # Patch reactor used by schedulelib, because we don't use it in this
        # test and it is only costing us performance.
        # The patching has to be done here because reloadDatabases() reloads
        # all the modules.
        schedulelib.reactor = DummyReactor()
        scheduleview.configDB = configlib.configDB
        # Create singleton instance.
        schedulelib.ScheduleManager()

        self.__taskRunnerAvailableCallbacks = []
        self.__timedCallbacks = []

        # Note: This must happen before the Task Runners are generated,
        #       otherwise their initial sync time is not valid.
        #       It must also happen before the job observer is registered,
        #       because that will check the current time.
        self.__currentTime = self.preparedTime
        setTimeFunc(self.getTime)

        self.jobs = []
        joblib.jobDB.addObserver(self)

        class CustomGenerator(DataGenerator):
            numTasks = 1
            numInputs = [ 0 ]
            numOutputs = [ 0 ]

        self.dataGenerator = gen = CustomGenerator()
        gen.createDefinitions()

        gen.createTaskRunners()
        trRecord = resourcelib.resourceDB.get(gen.taskRunners[0])
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

    def tearDown(self):
        removeRec(cfg.dbDir)

    def reloadDatabases(self):
        databases.reloadDatabases()

    def createConfig(self):
        '''Create a job configuration.
        '''
        return self.dataGenerator.createConfiguration()

    def defaultConfigFactory(self):
        '''Default implementation of "configFactory" as used by
        createSchedule(). It calls createConfig() to create a single config.
        '''
        config = self.createConfig()
        self.assertEqual(len(configlib.configDB), 1)
        return { 'configId': config.getId() }

    def createSchedule(
        self, scheduleId, suspended, startTime, sequence,
        owner = 'test_user', days = None, comment = 'this is a comment',
        configFactory = None
        ):
        if configFactory is None:
            configFactory = self.defaultConfigFactory
        properties =  {
            'id': scheduleId, 'suspended': str(suspended),
            'startTime': startTime, 'sequence': sequence,
            'owner': owner,
            'minDelay': self.continuousDelay // 60
            }
        if days is not None:
            properties['days'] = days
        properties.update(configFactory())
        element = schedulelib.Scheduled(properties, comment, True)
        schedulelib.scheduleDB.add(element)
        return element

    def expectedStatus(self):
        # TODO: Add tests that check handling of status "error".
        if self.__nrCreatedJobs > self.__nrFinishedJobs:
            return 'running'
        elif self.__isDone:
            return 'done'
        elif self.__missingConfig or not self.scheduled.getMatchingConfigIds():
            return 'warning'
        elif self.__suspended:
            return 'suspended'
        else:
            return 'ok'

    def checkStatus(self):
        schedule = self.scheduled
        self.assertEqual(
            schedule.isRunning(),
            self.__nrCreatedJobs > self.__nrFinishedJobs
            )
        self.assertEqual(schedule.isDone(), self.__isDone)
        if self.__missingConfig:
            self.assertEqual(len(schedule.getMatchingConfigIds()), 0)
        self.assertEqual(schedule.isSuspended(), self.__suspended)
        self.assertEqual(getScheduleStatus(schedule), self.expectedStatus())
        self.assertEqual(len(joblib.jobDB), self.__nrCreatedJobs)
        finishedJobs = [
            job for job in joblib.jobDB if job.isExecutionFinished()
            ]
        self.assertEqual(len(finishedJobs), self.__nrFinishedJobs)

    def getTime(self):
        return self.__currentTime

    def advanceTo(self, newTime):
        assert self.__currentTime <= newTime, (
            'test code tries to go back in time: from %d to %d'
            % ( self.__currentTime, newTime )
            )
        assert self.__currentTime % 60 == 0
        assert newTime % 60 == 0
        schedulelib.ScheduleManager.instance.trigger()
        self.__performCallbacks()
        while self.__currentTime < newTime:
            self.checkStatus()
            #print 'time %d -> %d' % ( self.getTime(), self.getTime() + 30 )
            # Events always happen on minute boundaries, so by using half-minute
            # steps we ensure that we always check the state in between two
            # events that do not occur simultaneously.
            self.__currentTime += 30
            schedulelib.ScheduleManager.instance.trigger()
            self.__performCallbacks()

    def wait(self, seconds):
        self.advanceTo(self.__currentTime + seconds)

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
        self.assertEqual(len(schedulelib.scheduleDB), 0)
        schedId = 'schedule-name'
        if configFactory is None and missingConfig:
            configFactory = sharedConfigFactory('nonExisting')
        element = self.createSchedule(
            schedId, suspended, self.preparedTime + deltaTime,
            sequence, days = days, configFactory = configFactory
            )
        self.scheduled = scheduled = schedulelib.scheduleDB.get(schedId)
        self.assertTrue(element is scheduled, (element, scheduled))

        # Verify initial status.
        self.checkStatus()

    def expectRunning(self, numJobs = 1):
        self.__nrCreatedJobs += numJobs

    def expectJobDone(self):
        self.__nrFinishedJobs += 1

    def expectScheduleDone(self):
        self.__isDone = True

class Test0100Basic(ScheduleFixtureMixin, unittest.TestCase):
    '''Test a few basic scenarios for using schedulelib.
    '''

    def __init__(self, methodName = 'runTest'):
        ScheduleFixtureMixin.__init__(self)
        unittest.TestCase.__init__(self, methodName)

    def test0100NonExistingOnce(self):
        '''Test one-shot schedule with a non-existing config.
        '''
        self.prepare(-120, 'once', missingConfig = True)
        self.expectScheduleDone()
        self.wait(60)

    def test0105NonExistingRepeat(self):
        '''Test daily schedule with a non-existing config.
        '''
        self.prepare(-120, 'daily', missingConfig = True)
        self.wait(60)

    def test0110NonExistingSuspended(self):
        '''Test one-shot schedule with a non-existing config, which is suspended.
        '''
        self.prepare(-120, 'once', missingConfig = True, suspended = True)
        self.wait(60)

    def test0200OnceSuspended(self):
        '''Test one-shot schedule which is suspended.
        '''
        self.prepare(-120, 'once', suspended = True)
        self.wait(60)

    def test0210OnceFuture(self):
        '''Test one-shot schedule with a start time in the future.
        '''
        self.prepare(120, 'once')
        self.wait(60)

    def test0220OncePast(self):
        '''Test one-shot schedule with a start time in the past.
        '''
        self.prepare(-120, 'once')
        self.expectScheduleDone()
        self.expectRunning()
        self.wait(60)
        self.assertEqual(self.scheduled['lastStartTime'], self.preparedTime)

    def test0230OnceStart(self):
        '''Test that a one-shot schedule is started at the specified time.
        '''
        startOffset = 120
        self.prepare(startOffset, 'once')
        self.wait(startOffset)
        self.expectRunning()
        self.expectScheduleDone()
        self.wait(60)
        self.assertEqual(
            self.scheduled['lastStartTime'], self.preparedTime + startOffset
            )

    def test0300ContinuousStart(self):
        '''Test that a continuous schedule is started repeatedly.
        '''
        startOffset = 120
        self.prepare(startOffset, sequence = 'continuously')
        self.wait(startOffset)
        for loop_ in range(4):
            self.expectRunning()
            self.wait(self.duration)
            self.expectJobDone()

    def runContinuousStartDelay(self, startOffset):
        self.duration = 120
        self.prepare(startOffset, sequence = 'continuously')
        self.wait(startOffset)
        for loop_ in range(4):
            self.expectRunning()
            self.wait(self.duration)
            self.expectJobDone()
            self.wait(self.continuousDelay - self.duration)

    def test0310ContinuousStartDelay(self):
        '''Test minimum delay between jobs started by continuous schedule.
        '''
        self.runContinuousStartDelay(120)

    def test0311ContinuousStartDelayASAP(self):
        '''Test minimum delay between jobs started by continuous schedule.
        Similar to the previous test, but using startOffset 0, because we once
        had a bug that only occurred when start time is ASAP.
        '''
        self.runContinuousStartDelay(0)

    def test0320ContinuousSuspend(self):
        '''Test suspending a continous schedule.
        '''
        startOffset = 120
        self.prepare(startOffset, sequence = 'continuously')
        self.wait(startOffset)
        for loop_ in range(4):
            self.expectRunning()
            self.wait(60)
            self.setSuspend(True)
            self.wait(self.duration - 60)
            self.expectJobDone()
            self.wait(60)
            self.setSuspend(False)

    def test0330ContinuousDelete(self):
        '''Test deletion of a continous schedule during execution.
        '''
        # Let the schedule run for a while.
        self.test0310ContinuousStartDelay()
        # Delete schedule.
        self.expectRunning()
        self.wait(60)
        schedulelib.scheduleDB.remove(self.scheduled)
        self.assertEqual(len(schedulelib.scheduleDB), 0)
        self.wait(self.duration - 60)
        self.expectJobDone()
        # Run for another day, no jobs should be created anymore.
        self.assertEqual(len(joblib.jobDB), 5)
        self.wait(secondsPerDay)
        self.assertEqual(len(joblib.jobDB), 5)

class Test0400StartTime(ScheduleFixtureMixin, unittest.TestCase):
    '''Test cases which validate the time at which schedules are started.
    '''
    # Start Monday 2007-01-01 at midnight.
    preparedTime = int(time.mktime(( 2007, 1, 1, 0, 0, 0, 0, 1, 0 )))

    def __init__(self, methodName = 'runTest'):
        ScheduleFixtureMixin.__init__(self)
        unittest.TestCase.__init__(self, methodName)

    def checkStatus(self):
        # The default implementation of this method assumes there is only one
        # schedule, which is not true for most test cases in this class.
        pass
        # We could perform the check below, but it slows down the test a lot
        # and it doesn't provide much value in return.
        #for schedule in schedulelib.scheduleDB:
        #    self.assertEqual(getScheduleStatus(schedule), 'ok')

    def test0400DailyStart(self):
        '''Test daily schedule.
        '''
        # Schedule starts Monday 2007-01-01 at 13:01.
        startTime = int(time.mktime(( 2007, 1, 1, 13, 1, 0, 0, 0, 0 )))
        self.prepare(startTime - self.preparedTime, sequence = 'daily')
        self.assertEqual(getScheduleStatus(self.scheduled), 'ok')

        # Run simulation for 1 week.
        self.wait(secondsPerWeek)

        # Validate the results.
        creationTimes = [ job['timestamp'] for job in self.jobs ]
        self.assertEqual(len(creationTimes), 7)
        for i in range(6):
            self.assertEqual(
                creationTimes[i + 1] - creationTimes[i], secondsPerDay,
                'There are not 24*60*60 seconds between two job runs'
                )

    def test0410DailyOverflow(self):
        '''Test what happens if a job started from a daily schedule runs for
        longer than a day.
        '''
        # Each job takes 40 hours to execute.
        self.duration = 40 * 60 * 60

        # For non-continuous schedules, it does not matter whether the job
        # has finished executing, so this schenario should behave the same
        # as the previous one.
        self.test0400DailyStart()

    def test0500WeeklyStart(self):
        '''Test weekly schedules with one day each.
        '''
        configId = self.createConfig().getId()

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
            self.createSchedule(
                schedId, False, startTime,
                'weekly', days = '0' * day + '1' + '0' * (6 - day),
                configFactory = sharedConfigFactory(configId)
                )
            scheduled = schedulelib.scheduleDB.get(schedId)
            self.assertEqual(getScheduleStatus(scheduled), 'ok')

        # Run simulation for 2 weeks.
        self.wait(2 * secondsPerWeek)

        # Validate the results.
        self.assertEqual(set(joblib.jobDB), set(self.jobs))
        creationTimes = [ job['timestamp'] for job in self.jobs ]
        self.assertEqual(len(creationTimes), 14)
        self.assertEqual(len(scheduledTimes), 7)
        for day in range(7):
            self.assertEqual(
                creationTimes[day], scheduledTimes[day],
                'Job did not start at scheduled time'
                )
            self.assertEqual(
                creationTimes[7 + day] - creationTimes[day], secondsPerWeek,
                'There is not exactly 1 week between two job runs'
                )

    def test0510WeeklyStartMultiDay(self):
        '''Test weekly schedules with multiple days.
        '''
        configId = self.createConfig().getId()

        # Create 2 schedules: Mon/Wed/Fri/Sun and Tue/Thu/Sat.
        scheduledTimes = []
        for i, dayString in enumerate(('1010101', '0101010')):
            startTime = int(time.mktime(
                ( 2007, 1, 1 + i, 13, 1 + i * 2, 0, 0, 1, 0 )
                ))
            scheduledTimes.append(startTime)
            schedId = 'WeeklyStartMultiDay_%d' % i
            self.createSchedule(
                schedId, False, startTime, 'weekly', days = dayString,
                configFactory = sharedConfigFactory(configId)
                )
            scheduled = schedulelib.scheduleDB.get(schedId)
            self.assertEqual(getScheduleStatus(scheduled), 'ok')

        # Run simulation for 2 weeks.
        self.wait(2 * secondsPerWeek)

        # Validate the results.
        self.assertEqual(set(joblib.jobDB), set(self.jobs))
        creationTimes = [ job['timestamp'] for job in self.jobs ]
        self.assertEqual(len(creationTimes), 14)
        self.assertEqual(len(scheduledTimes), 2)
        for i in range(2):
            self.assertEqual(
                creationTimes[i], scheduledTimes[i],
                'Job did not start at scheduled time'
                )
        for day in range(7):
            self.assertEqual(
                creationTimes[7 + day] - creationTimes[day], secondsPerWeek,
                'There is not exactly 1 week between two job runs'
                )

    def test0520WeeklyStartCorrection(self):
        '''Test weekly schedule for which the start time should be corrected
        to the next available selected day.
        '''
        configId = self.createConfig().getId()

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
            self.createSchedule(
                schedId, False, startTime, 'weekly', days = '0010000',
                configFactory = sharedConfigFactory(configId)
                )
            scheduled = schedulelib.scheduleDB.get(schedId)
            self.assertEqual(getScheduleStatus(scheduled), 'ok')

        # Run simulation for 4 weeks.
        self.wait(4 * secondsPerWeek)

        # Validate the results.
        self.assertEqual(set(joblib.jobDB), set(self.jobs))
        for schedId, scheduledTime, correctedTime in scheduledTimes:
            jobsFromSchedule = [
                job for job in self.jobs if job.getScheduledBy() == schedId
                ]
            self.assertTrue(3 <= len(jobsFromSchedule) <= 4, jobsFromSchedule)
            prevCreationTime = None
            for job in jobsFromSchedule:
                creationTime = job['timestamp']
                if prevCreationTime is None:
                    self.assertTrue(scheduledTime <= creationTime, '%s > %s' %
                        ( formatTime(scheduledTime), formatTime(creationTime) )
                        )
                    self.assertEqual(creationTime, correctedTime, '%s != %s' %
                        ( formatTime(creationTime), formatTime(correctedTime) )
                        )
                else:
                    self.assertEqual(
                        creationTime - prevCreationTime, secondsPerWeek,
                        'There is not exactly 1 week between two job runs'
                        )
                prevCreationTime = creationTime

class TaggedConfigFactory:

    tagKey = 'keymaster'
    tagValue = 'gatekeeper'

    def __init__(self, dataGenerator, numConfigs):
        self.configs = [
            dataGenerator.createConfiguration(name = 'config%d' % count)
            for count in range(numConfigs)
            ]
        project.setTagKeys(( self.tagKey, ))

    def __call__(self):
        return { 'tagKey': self.tagKey, 'tagValue': self.tagValue }

    def setTags(self):
        for config in self.configs:
            config.setTag(self.tagKey, (self.tagValue, ))
            # Force tag cache update.
            config._notify()

class Test0600Tagged(ScheduleFixtureMixin, unittest.TestCase):
    '''Test cases which validate scheduling by configuration tag.
    Only the tagging specific parts are checked, because the mechanisms that
    determine the moment of instantiation are the same as for scheduling by
    name.
    '''

    def __init__(self, methodName = 'runTest'):
        ScheduleFixtureMixin.__init__(self)
        unittest.TestCase.__init__(self, methodName)

    def test0600NonMatching(self):
        '''Test firing a schedule with a tag that does not match any configs.
        '''
        def configFactory():
            return { 'tagKey': 'nosuchkey', 'tagValue': 'dummy' }
        startOffset = 120
        self.prepare(startOffset, 'once', configFactory = configFactory)
        self.assertEqual(len(self.scheduled.getMatchingConfigIds()), 0)
        self.wait(startOffset)
        self.expectScheduleDone()
        self.wait(60)
        self.assertIsNone(self.scheduled['lastStartTime'])

    def prepareTaggedStart(self, sequence, numConfigs, configFactory = None):
        if configFactory is None:
            configFactory = TaggedConfigFactory(self.dataGenerator, numConfigs)
        startOffset = 120
        # Preparation.
        self.prepare(startOffset, sequence, configFactory = configFactory)
        self.startTime = self.preparedTime + startOffset
        # Apply tag.
        self.assertEqual(len(self.scheduled.getMatchingConfigIds()), 0)
        configFactory.setTags()
        self.assertEqual(len(self.scheduled.getMatchingConfigIds()), numConfigs)
        # Execution.
        self.wait(startOffset)

    def runTaggedStart(self, numConfigs, configFactory = None):
        if configFactory is None:
            configFactory = TaggedConfigFactory(self.dataGenerator, numConfigs)
        self.prepareTaggedStart('once', numConfigs, configFactory)
        self.expectRunning(numJobs = numConfigs)
        self.expectScheduleDone()
        self.wait(60)
        self.assertEqual(
            self.scheduled['lastStartTime'], self.startTime
            )
        # Verify last started jobs.
        createdConfigs = set(
            config.getId() for config in configFactory.configs
            )
        jobConfigs = set(
            joblib.jobDB[jobId].configId
            for jobId in self.scheduled.getLastJobs()
            )
        self.assertEqual(createdConfigs, jobConfigs)

    def test0610SingleMatch(self):
        '''Test firing a schedule with a tag that matches a single config.
        '''
        self.runTaggedStart(1)

    def test0620MultiMatch(self):
        '''Test firing a schedule with a tag that matches multiple configs.
        '''
        self.runTaggedStart(2)

    def test0700TagCaseInsensitive(self):
        '''Test whether tag values are case insensitive.
        '''
        class ConfigFactory(TaggedConfigFactory):
            def __call__(self):
                properties = TaggedConfigFactory.__call__(self)
                tagValue = properties['tagValue']
                newTagValue = tagValue.capitalize()
                assert newTagValue != tagValue
                properties['tagValue'] = newTagValue
                return properties
        self.runTaggedStart(2, ConfigFactory(self.dataGenerator, 2))

    def test0710ContinuousMulti(self):
        '''Test repeating of continuous schedule which matches multiple configs.
        '''
        numConfigs = 2
        self.prepareTaggedStart('continuously', numConfigs)
        for loop_ in range(4):
            self.expectRunning(numJobs = numConfigs)
            self.wait(self.duration)
            self.expectJobDone()
            self.wait(self.duration)
            self.expectJobDone()

    def test0720ContinuousMultiDelay(self):
        '''Test minimum delay of continuous schedule based on tag.
        '''
        self.duration = 120
        numConfigs = 2
        self.prepareTaggedStart('continuously', numConfigs)
        for loop_ in range(4):
            self.expectRunning(numJobs = numConfigs)
            self.wait(self.duration)
            self.expectJobDone()
            self.wait(self.duration)
            self.expectJobDone()
            self.wait(self.continuousDelay - self.duration * 2)

if __name__ == '__main__':
    unittest.main()

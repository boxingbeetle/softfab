# SPDX-License-Identifier: BSD-3-Clause

'''
A schedule should run when:
- once: time >= start_time && !done
- daily/weekly: time >= start_time
- continuous: time >= start_time && !running
- passive: time >= start_time && flag && !running
There is a feature request to make continuous schedules run only in specified
time slots. Although this does not have to be implemented yet, the design
should leave this option open.

Start time can be:
- timestamp
- never
- asap

New start time is calculated like this:
- once: never
- daily/weekly: start_time + N
  (actually it is slightly more complex because of daylight saving time)
- continuous: start_time + minimum_delay
- passive: asap

Q&A:
Q: Should "never" and "asap" be visible on the UI, or use just "-" for both?
A: When sorting by next run, it would be useful to have "asap" at the start of
   the list and "never" at the end. Without making the difference visible, it
   would be strange that one "-" is at the start and another "-" is at the end.
Q: Should minimum delay for continuous schedule increase the start time?
A: If we start presenting tentative start times (>=), doing this makes sense.
Q: Should passive schedule have a minimum delay?
A: Passive schedules are an alternative to LoadExecuteDefault, which is not
   limited either. Actually, passive schedules are already better protected
   against overflowing the job queue since the previous job has to be finished
   before a new one is created.
Q: Should passive schedule have a start time? (other than asap)
A: It should be consistent with continuous schedules. For continuous we
   eventually want to execute them in time slots; a start time is a primitive
   precursor to that. Passive schedule + time slot could be used for a
   conditional daily test: at night a test is started if the API call was made
   during the day, otherwise the test is skipped.
Q: Should daily/weekly schedules run if the previous one was not finished yet?
A: When selecting configurations by tag it is possible one started job is not
   finished yet, but all the others have. Starting nothing at all because one
   job is stuck is probably not what the user wants.
Q: If 0 jobs are created on a trigger (for example, no matching configs),
   should that count as "last run"?
A: No, only if one or more jobs are created. This makes it easier to diagnose
   problems.
Q: What happens if a schedule is triggered when suspended?
A: For repeating schedules, advance to next time.
   For non-repeating schedules, run as soon as schedule is resumed.
'''

from softfab.config import dbDir
from softfab.configlib import Config, configDB, iterConfigsByTag
from softfab.databaselib import Database, DatabaseElem, RecordObserver
from softfab.joblib import jobDB
from softfab.selectlib import ObservingTagCache, Selectable
from softfab.timelib import endOfTime, getTime
from softfab.utils import Heap, SharedInstance
from softfab.xmlbind import XMLTag
from softfab.xmlgen import xml

from twisted.internet import reactor

from enum import Enum
from typing import ClassVar
import logging
import time

asap = 0 # Schedule runs as soon as possible.

class ScheduleRepeat(Enum):
    """Ways in which a schedule can repeat.
    """
    ONCE = 1
    DAILY = 2
    WEEKLY = 3
    CONTINUOUSLY = 4
    PASSIVE = 5

class ScheduledFactory:
    @staticmethod
    def createScheduled(attributes):
        return Scheduled(attributes)

class ScheduleDB(Database):
    baseDir = dbDir + '/scheduled'
    factory = ScheduledFactory()
    privilegeObject = 's'
    description = 'schedule'
    uniqueKeys = ( 'id', )
scheduleDB = ScheduleDB()

class JobDBObserver(RecordObserver):
    '''Send notifications if a job related to a schedule is new or changed.
    '''
    instance = SharedInstance() # type: ClassVar[SharedInstance]

    def __init__(self):
        RecordObserver.__init__(self)
        self.__observers = []
        jobDB.addObserver(self)

    def addObserver(self, observer):
        self.__observers.append(observer)

    def added(self, record):
        self.updated(record)

    def removed(self, record):
        assert False, 'job %s removed' % record.getId()

    def updated(self, record):
        schedId = record.getScheduledBy()
        if schedId is not None:
            schedule = scheduleDB.get(schedId) # schedule might be deleted
            if schedule is not None:
                for observer in self.__observers:
                    observer(record, schedule)

class ScheduleManager(RecordObserver):
    instance = None # Singleton instance.

    def __init__(self):
        RecordObserver.__init__(self)
        # Initialise singleton instance.
        assert ScheduleManager.instance is None
        ScheduleManager.instance = self

        self.__heap = None
        self.__initHeap()

        scheduleDB.addObserver(self)
        JobDBObserver.instance.addObserver(self.__jobUpdated)

    def __initHeap(self):
        self.__heap = Heap(key=lambda schedule:
            (schedule['startTime'], schedule._properties['id'])
            )
        for schedule in scheduleDB:
            self.added(schedule)

    def __jobUpdated(self, job, schedule):
        if job.isExecutionFinished() and job.getId() in schedule.getLastJobs() \
                and not schedule.isRunning():
            # The schedule itself has not changed, but the return value of
            # isBlocked() might have.
            self.updated(schedule)

    def __addToQueue(self, record):
        if not record.isBlocked():
            self.__heap.add(record)
            # If the new schedule should start right away, trigger it.
            # Doing this call via the reactor makes sure that no schedules
            # are instantiated on upgrade.
            reactor.callLater(0, self.__triggerSchedules, getTime())

    def __removeFromQueue(self, record):
        try:
            self.__heap.remove(record)
        except ValueError:
            pass

    def __triggerSchedules(self, untilSecs):
        '''Create jobs for all schedules which have a start time that is
        before or equal to 'untilSecs'.
        '''
        # Checks if smallest item in heap is lower than current time.
        # If yes, clone and change 'startTime' in the database.
        while True:
            nextSchedule = self.__heap.peek()
            if nextSchedule is None or nextSchedule['startTime'] > untilSecs:
                break
            next(self.__heap)
            nextSchedule.trigger(untilSecs)

    def added(self, record):
        self.__addToQueue(record)

    def removed(self, record):
        self.__removeFromQueue(record)

    def updated(self, record):
        self.__removeFromQueue(record)
        self.__addToQueue(record)

    def trigger(self, scheduledMinute = 0):
        currentSecs = getTime()
        currentMinute = currentSecs // 60
        # If the call comes just before the minute boundary, trust the
        # scheduled minute instead of the current minute.
        minute = max(currentMinute, scheduledMinute)
        try:
            self.__triggerSchedules(minute * 60)
        finally:
            # Register callback at the next minute boundary.
            reactor.callLater(
                (minute + 1) * 60 - currentSecs,
                self.trigger,
                minute + 1
                )

class Scheduled(XMLTag, DatabaseElem, Selectable):
    '''A configuration that is scheduled for (repeated) execution.
    '''
    tagName = 'scheduled'
    intProperties = ('startTime', 'minDelay')
    enumProperties = {'sequence': ScheduleRepeat}
    cache = ObservingTagCache(scheduleDB, lambda: ('sf.cmtrigger',) )

    def __init__(self, properties, comment = '', adjustTime = False):
        assert 'configId' in properties \
            or ('tagKey' in properties and 'tagValue' in properties)
        # COMPAT 2.16: Rename 'paused' to 'suspended'.
        if 'paused' in properties:
            properties = dict(properties, suspended=properties['paused'])
            del properties['paused']

        XMLTag.__init__(self, properties)
        DatabaseElem.__init__(self)
        Selectable.__init__(self)
        self.__lastJobIds = []
        # Cached value: True means "might be running", False means "certainly
        # not running", since jobs can go from not fixed to fixed but not
        # vice versa.
        self.__running = True

        sequence = self._properties['sequence']
        if sequence is ScheduleRepeat.ONCE:
            self._properties['done'] = self._properties.get('done') == 'True'
        else:
            assert 'done' not in self._properties
        if sequence is ScheduleRepeat.PASSIVE:
            self._properties['trigger'] = (
                self._properties.get('trigger') == 'True'
                )
        else:
            assert 'trigger' not in self._properties
        self._properties['suspended'] = \
            self._properties.get('suspended') not in (None, '0', 'False')
        if not self._properties.get('owner'):
            self._properties['owner'] = None
        if sequence is ScheduleRepeat.CONTINUOUSLY:
            self._properties.setdefault('minDelay', 10)
        elif 'minDelay' in self._properties:
            del self._properties['minDelay']
        self.__comment = comment

        if adjustTime:
            self.__adjustStartTime(False)

    def __getitem__(self, key):
        if key == 'startTime':
            startTime = self._properties.get('startTime')
            if startTime is None:
                return endOfTime if self.isDone() else asap
            else:
                return startTime
        elif key == 'configId':
            # configId is None if this schedule is based on tags.
            return self._properties.get('configId')
        elif key == 'tagValue':
            # Return the current display value.
            tagKey = self._properties['tagKey']
            tagValue = self._properties['tagValue']
            cvalue_, dvalue = Config.cache.toCanonical(tagKey, tagValue)
            return dvalue
        elif key == 'days':
            return self._properties.get('days', '')
        elif key == 'comment':
            return self.__comment
        elif key == 'owner':
            return self.getOwner()
        elif key == 'lastStartTime':
            return self.getLastStartTime()
        else:
            return self._properties[key]

    def _addLastJob(self, jobId):
        if jobDB.get(jobId) is not None:
            # We sometimes clean up old jobs by manually removing records from
            # the database, so in those cases the job may no longer exist.
            self.__lastJobIds.append(jobId)

    def _addJob(self, attributes):
        self._addLastJob(attributes['jobId'])

    def _textComment(self, text):
        self.__comment = text

    def getId(self):
        return self._properties['id']

    def getLastJobs(self):
        '''Returns the job IDs of the last set of jobs started by this schedule.
        '''
        return tuple(self.__lastJobIds)

    def getOwner(self):
        """Gets the owner of this scheduled job,
        or None if this job does not have an owner.
        """
        return self._properties.get('owner')

    @property
    def comment(self):
        """Gets user-specified comment string for this schedule.
        Comment string may contain newlines.
        """
        return self.__comment

    def isBlocked(self):
        '''Return True iff this schedule cannot be triggered in its current
        state. Note that triggering is different from running: for example
        a daily schedule can be triggered when suspended, in that case it will
        skip one day.
        '''
        sequence = self._properties['sequence']
        if sequence is ScheduleRepeat.ONCE:
            return self.isDone() or self.isSuspended()
        elif sequence is ScheduleRepeat.CONTINUOUSLY:
            return self.isRunning() or self.isSuspended()
        elif sequence is ScheduleRepeat.PASSIVE:
            return not self._properties['trigger'] or self.isRunning() \
                or self.isSuspended()
        else:
            return False

    def isDone(self):
        '''Returns True iff this schedule will not run again.
        '''
        return self._properties.get('done', False)

    def isSuspended(self):
        '''Returns True iff this schedule is suspended.
        '''
        return self._properties['suspended']

    def isRunning(self):
        '''Returns True iff one or more of the jobs last instantiated by this
        schedule are not finished yet.
        '''
        if not self.__running:
            return False
        for jobId in self.__lastJobIds:
            if not jobDB[jobId].isExecutionFinished():
                return True
        self.__running = False
        return False

    def setSuspend(self, suspended):
        '''Suspends or resumes a schedule.
        '''
        if not isinstance(suspended, bool):
            raise TypeError(
                'Expected bool for "suspended" argument, got "%s"'
                % type(suspended).__name__
                )
        if self._properties['suspended'] != suspended:
            self._properties['suspended'] = suspended
            self._notify()

    def setTrigger(self):
        '''Sets the trigger on a passive schedule.
        Raises ValueError if this is not a passive schedule.
        '''
        if self._properties['sequence'] is not ScheduleRepeat.PASSIVE:
            raise ValueError('Not a passive schedule')
        if not self._properties['trigger']:
            self._properties['trigger'] = True
            self._notify()

    def getLastStartTime(self):
        '''Returns the create time of the most recently created jobs,
        or 0 if the schedule never created any jobs.
        '''
        createTime = 0
        for jobId in self.__lastJobIds:
            # Typically all jobs will have the same create time.
            createTime = max(createTime, jobDB[jobId].getCreateTime())
        return createTime

    def __adjustStartTime(self, skipToNext, currentTime = None):
        '''Calculate time of next scheduled job.
        If 'skipToNext' is True, the time is advanced one time period (for
        periodic schedules) or set to 0 (for non-periodic schedules);
        if 'skipToNext' is False, the current start time is rounded to a
        period boundary (for periodic schedules) or clipped to the current time
        (for non-periodic schedules).
        Passing currentTime is useful if the actual current time can be
        slightly before the minute boundary (see ScheduleManager.trigger()).
        '''
        if currentTime is None:
            currentTime = getTime()
        startTime = self._properties.get('startTime')
        sequence = self._properties['sequence']

        if startTime is None:
            # Start time can be None if a schedule is done or should start ASAP.
            assert sequence not in (ScheduleRepeat.DAILY, ScheduleRepeat.WEEKLY)

            if not skipToNext:
                # There is nothing to adjust.
                return
            # For continuous schedules started ASAP, it is essential to compute
            # the next start time because of the minimum delay feature.

        elif currentTime < startTime:
            # In theory forced skip and future start time would be possible,
            # but we have no use for it and therefore don't support it.
            assert not skipToNext

            if sequence is not ScheduleRepeat.WEEKLY:
                # Any start time in the future is fine as-is.
                return

        if sequence is ScheduleRepeat.ONCE:
            nextTime = None
        elif sequence is ScheduleRepeat.CONTINUOUSLY:
            assert startTime is None or currentTime >= startTime
            if skipToNext:
                nextTime = ( # round up to minute boundary
                    (currentTime + 59) // 60 + self._properties['minDelay']
                    ) * 60
            else:
                nextTime = None
        elif sequence is ScheduleRepeat.PASSIVE:
            nextTime = None
        else:
            if sequence is ScheduleRepeat.WEEKLY:
                dayFlags = self._properties['days']
                assert '1' in dayFlags and len(dayFlags) == 7
            else:
                dayFlags = '1' * 7
                assert sequence is ScheduleRepeat.DAILY
            nextTimeList = list(time.localtime(startTime))
            nextTimeList[8] = -1 # local time: no time zone
            if startTime is None or currentTime >= startTime:
                # Set day to today.
                nextTimeList[ : 3] = time.localtime(currentTime)[ : 3]
                if skipToNext:
                    # Move ahead at least one day.
                    nextTimeList[2] += 1
            nextTime = int(time.mktime(tuple(nextTimeList)))
            while nextTime < currentTime \
               or dayFlags[time.localtime(nextTime)[6]] != '1':
                nextTimeList[2] += 1
                nextTime = int(time.mktime(tuple(nextTimeList)))
        self._properties['startTime'] = nextTime

    def getMatchingConfigIds(self):
        '''Returns the IDs of configurations that will be instantiated by this
        schedule, if the schedule would be triggered right now.
        '''
        configId = self._properties.get('configId')
        if configId is None:
            key = self._properties['tagKey']
            value = self._properties['tagValue']
            return tuple(
                config.getId()
                for config in iterConfigsByTag(key, value)
                )
        else:
            if configId in configDB:
                return (configId,)
            else:
                # Nowadays we no longer allow deletion of the config a schedule
                # refers to it, but there may be old databases in which there
                # are schedules that point to non-existing configs.
                return ()

    def trigger(self, currentTime):
        # To avoid an infinite loop in ScheduleManager, each invocation of
        # trigger() should either increase the schedule's start time or
        # cause isBlocked() to return False (which will lead to the schedule
        # being removed from the heap).

        # Advance time for next run.
        self.__adjustStartTime(True, currentTime)
        try:
            if not self.isSuspended():
                sequence = self._properties['sequence']
                if sequence is ScheduleRepeat.ONCE:
                    self._properties['done'] = True
                elif sequence is ScheduleRepeat.PASSIVE:
                    self._properties['trigger'] = False
                self.__createJobs()
        finally:
            # Make sure the schedule is updated in the DB even if job creation
            # failed.
            self._notify()

    def __createJobs(self):
        # Create job from each matched configuration.
        jobIds = []
        for configId in self.getMatchingConfigIds():
            try:
                config = configDB[configId]
                if config.hasValidInputs():
                    job = config.createJob(self['owner'])
                    job.comment += '\n' + self.comment
                    job.setScheduledBy(self.getId())
                    jobDB.add(job)
                    jobIds.append(job.getId())
                else:
                    logging.warning(
                        'Schedule "%s" could not instantiate '
                        'configuration "%s" because it is inconsistent',
                        self.getId(), configId
                        )
            except Exception:
                # Make sure a failure to instantiate one config does not
                # prevent other configs from being instantiated.
                logging.exception(
                    'Schedule "%s" failed to instantiate configuration "%s"',
                    self.getId(), configId
                    )
        # Update "last run" if any jobs were created.
        if jobIds:
            self.__lastJobIds = jobIds
            self.__running = True

    def _getContent(self):
        yield xml.comment[ self.__comment ]
        for jobId in self.__lastJobIds:
            yield xml.job(jobId = jobId)
        yield self._tagsAsXML()

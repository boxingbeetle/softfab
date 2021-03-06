# SPDX-License-Identifier: BSD-3-Clause

'''
A schedule should run when:
- once: time >= start_time && !done
- daily/weekly: time >= start_time
- continuous: time >= start_time && !running
- triggered: time >= start_time && flag && !running
There is a feature request to make continuous schedules run only in specified
time slots. Although this does not have to be implemented yet, the design
should leave this option open.

New start time is calculated like this:
- once: never
- daily/weekly: start_time + N
  (actually it is slightly more complex because of daylight saving time)
- continuous: start_time + minimum_delay
- triggered: asap

Q&A:
Q: Should "never" and "asap" be visible on the UI, or use just "-" for both?
A: When sorting by next run, it would be useful to have "asap" at the start of
   the list and "never" at the end. Without making the difference visible, it
   would be strange that one "-" is at the start and another "-" is at the end.
Q: Should minimum delay for continuous schedule increase the start time?
A: If we start presenting tentative start times (>=), doing this makes sense.
Q: Should triggered schedule have a minimum delay?
A: Triggered schedules are an alternative to LoadExecuteDefault, which is not
   limited either. Actually, triggered schedules are already better protected
   against overflowing the job queue since the previous job has to be finished
   before a new one is created.
Q: Should triggered schedule have a start time? (other than asap)
A: It should be consistent with continuous schedules. For continuous we
   eventually want to execute them in time slots; a start time is a primitive
   precursor to that. Triggered schedule + time slot could be used for a
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

from enum import Enum
from pathlib import Path
from typing import (
    Callable, Dict, Iterator, List, Mapping, MutableSet, Optional, Sequence,
    Tuple, cast
)
import logging
import time

from twisted.internet.interfaces import IReactorTime

from softfab.configlib import ConfigDB
from softfab.databaselib import Database, RecordObserver
from softfab.joblib import Job, JobDB
from softfab.selectlib import ObservingTagCache, SelectableRecordABC, TagCache
from softfab.timelib import endOfTime, getTime
from softfab.utils import Heap
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLAttributeValue, XMLContent, xml


def _listToTimestamp(timeList: Sequence[int]) -> int:
    assert len(timeList) == 9, timeList
    return int(time.mktime(cast(
        Tuple[int, int, int, int, int, int, int, int, int],
        tuple(timeList)
        )))

asap = 0 # Schedule runs as soon as possible.

class ScheduleRepeat(Enum):
    """Ways in which a schedule can repeat.
    """
    ONCE = 1
    DAILY = 2
    WEEKLY = 3
    CONTINUOUSLY = 4
    TRIGGERED = 5

class ScheduledFactory:
    @staticmethod
    def createScheduled(attributes: Mapping[str, str]) -> 'Scheduled':
        return Scheduled(attributes)

class ScheduleDB(Database['Scheduled']):
    privilegeObject = 's'
    description = 'schedule'
    uniqueKeys = ( 'id', )

    def __init__(self, baseDir: Path):
        super().__init__(baseDir, ScheduledFactory())
        self.tagCache: TagCache = ObservingTagCache(
            self, lambda: ('sf.trigger',)
            )

    def create(self,
               name: str,
               suspended: bool,
               startTime: int,
               repeat: ScheduleRepeat,
               owner: Optional[str],
               comment: str,
               extra: Mapping[str, XMLAttributeValue]
               ) -> 'Scheduled':
        return Scheduled(
            dict(extra,
                 id=name,
                 suspended=suspended,
                 startTime=startTime,
                 repeat=repeat,
                 owner=owner),
            comment, True)

class _JobDBObserver(RecordObserver[Job]):
    '''Send notifications if a job related to a schedule is new or changed.
    '''

    def __init__(self, scheduleDB: ScheduleDB):
        super().__init__()
        self.__scheduleDB = scheduleDB
        self.__observers: List[Callable[[Job, 'Scheduled'], None]] = []

    def addObserver(self, observer: Callable[[Job, 'Scheduled'], None]) -> None:
        self.__observers.append(observer)

    def added(self, record: Job) -> None:
        self.updated(record)

    def removed(self, record: Job) -> None:
        assert False, f'job {record.getId()} removed'

    def updated(self, record: Job) -> None:
        schedId = record.getScheduledBy()
        if schedId is not None:
            # Note that schedule might be deleted.
            schedule = self.__scheduleDB.get(schedId)
            if schedule is not None:
                for observer in self.__observers:
                    observer(record, schedule)

class ScheduleManager(RecordObserver['Scheduled']):

    def __init__(self,
                 configDB: ConfigDB,
                 jobDB: JobDB,
                 scheduleDB: ScheduleDB,
                 reactor: IReactorTime
                 ):
        super().__init__()
        self.configDB = configDB
        self.jobDB = jobDB
        self.__reactor = reactor

        self.__runningJobs: Dict[str, MutableSet[str]] = {}
        """Maps schedule ID to the set of job IDs it spawned on its last run
        that haven't finished yet.
        """

        # Initialize heap.
        self.__heap: Heap[Scheduled] = Heap(key=lambda schedule:
            (schedule.startTime, schedule.getId())
            )
        for schedule in scheduleDB:
            self.added(schedule)

        scheduleDB.addObserver(self)
        jobDBObserver = _JobDBObserver(scheduleDB)
        jobDBObserver.addObserver(self.__jobUpdated)
        jobDB.addObserver(jobDBObserver)

    def __jobUpdated(self, job: Job, schedule: 'Scheduled') -> None:
        if job.isExecutionFinished():
            scheduleId = schedule.getId()
            unfinishedJobIds = self.__runningJobs.get(scheduleId)
            if unfinishedJobIds is not None:
                unfinishedJobIds.discard(job.getId())
                if not unfinishedJobIds:
                    schedule._jobsFinished() # pylint: disable=protected-access
                    self.updated(schedule)

    def __addToQueue(self, schedule: 'Scheduled') -> None:
        # Have the jobs from the last run finished?
        jobDB = self.jobDB
        unfinishedJobIds = set()
        for jobId in schedule.getLastJobs():
            job = jobDB.get(jobId)
            if job is not None and not job.isExecutionFinished():
                unfinishedJobIds.add(jobId)
        if unfinishedJobIds:
            self.__runningJobs[schedule.getId()] = unfinishedJobIds
        else:
            schedule._jobsFinished() # pylint: disable=protected-access

        if not schedule.isBlocked():
            self.__heap.add(schedule)
            # If the new schedule should start right away, trigger it.
            # Doing this call via the reactor makes sure that no schedules
            # are instantiated on upgrade.
            self.__reactor.callLater(0, self.__triggerSchedules, getTime())

    def __removeFromQueue(self, schedule: 'Scheduled') -> None:
        try:
            self.__heap.remove(schedule)
        except ValueError:
            pass
        self.__runningJobs.pop(schedule.getId(), None)

    def __triggerSchedules(self, untilSecs: int) -> None:
        '''Create jobs for all schedules which have a start time that is
        before or equal to 'untilSecs'.
        '''
        # Checks if smallest item in heap is lower than current time.
        # If yes, clone and change 'startTime' in the database.
        heap = self.__heap
        while True:
            nextSchedule = heap.peek()
            if nextSchedule is None or nextSchedule.startTime > untilSecs:
                break
            heap.pop()
            try:
                jobIds = list(
                    nextSchedule.createJobs(self.configDB, self.jobDB)
                    )
            except Exception:
                # Make sure the schedule is updated in the DB even
                # if job creation failed.
                logging.exception('Error creating jobs from schedule "%s"',
                                  nextSchedule.getId())
                jobIds = []
            nextSchedule.trigger(untilSecs, jobIds)

    def added(self, record: 'Scheduled') -> None:
        self.__addToQueue(record)

    def removed(self, record: 'Scheduled') -> None:
        self.__removeFromQueue(record)

    def updated(self, record: 'Scheduled') -> None:
        self.__removeFromQueue(record)
        self.__addToQueue(record)

    def trigger(self, scheduledMinute: int = 0) -> None:
        currentSecs = getTime()
        currentMinute = currentSecs // 60
        # If the call comes just before the minute boundary, trust the
        # scheduled minute instead of the current minute.
        minute = max(currentMinute, scheduledMinute)
        try:
            self.__triggerSchedules(minute * 60)
        finally:
            # Register callback at the next minute boundary.
            self.__reactor.callLater(
                (minute + 1) * 60 - currentSecs,
                self.trigger,
                minute + 1
                )

class Scheduled(XMLTag, SelectableRecordABC):
    '''A configuration that is scheduled for (repeated) execution.
    '''
    tagName = 'scheduled'
    boolProperties = ('suspended',)
    intProperties = ('startTime', 'minDelay', 'lastRunTime')
    enumProperties = {'repeat': ScheduleRepeat}

    def __init__(self,
                 properties: Mapping[str, XMLAttributeValue],
                 comment: str = '',
                 adjustTime: bool = False
                 ):
        assert 'configId' in properties \
            or ('tagKey' in properties and 'tagValue' in properties)
        # COMPAT 2.16: Rename 'paused' to 'suspended'.
        if 'paused' in properties:
            properties = dict(properties, suspended=properties['paused'])
            del properties['paused']
        # COMPAT 2.x.x: Rename 'sequence' key to 'repeat'.
        #               Rename 'passive' value to 'triggered'.
        if 'sequence' in properties:
            repeat = properties['sequence']
            if repeat == 'passive':
                repeat = 'triggered'
            properties = dict(properties, repeat=repeat)
            del properties['sequence']

        super().__init__(properties)
        self.__lastJobIds: Sequence[str] = []

        # Note: ScheduleManager will update this via _jobsFinished()
        #       if jobs are no longer running.
        self.__running = True
        """True iff the jobs from the last run haven't all finished yet."""

        repeat = self._properties['repeat']
        if repeat is ScheduleRepeat.ONCE:
            self._properties['done'] = \
                cast(str, self._properties.get('done', '')).lower() == 'true'
        else:
            assert 'done' not in self._properties
        if repeat is ScheduleRepeat.TRIGGERED:
            self._properties['trigger'] = (
                cast(str, self._properties.get('trigger', '')).lower() == 'true'
                )
        else:
            assert 'trigger' not in self._properties
        if repeat is ScheduleRepeat.CONTINUOUSLY:
            self._properties.setdefault('minDelay', 10)
        elif 'minDelay' in self._properties:
            del self._properties['minDelay']
        self.__comment = comment

        if adjustTime:
            self.__adjustStartTime(False)

    def __getitem__(self, key: str) -> object:
        if key == 'startTime':
            return self.startTime
        elif key == 'configId':
            return self.configId
        elif key == 'tagValue':
            return self.tagValue
        elif key == 'days':
            return self._properties.get('days', '')
        elif key == 'comment':
            return self.__comment
        elif key == 'owner':
            return self.owner
        else:
            return self._properties[key]

    def _addLastJob(self, jobId: str) -> None:
        cast(List[str], self.__lastJobIds).append(jobId)

    def _addJob(self, attributes: Mapping[str, str]) -> None:
        self._addLastJob(attributes['jobId'])

    def _textComment(self, text: str) -> None:
        self.__comment = text

    def _jobsFinished(self) -> None:
        """Called by ScheduleManager when all jobs from the last run
        have finished.
        """
        self.__running = False

    def getId(self) -> str:
        return cast(str, self._properties['id'])

    def getLastJobs(self) -> Sequence[str]:
        '''Returns the job IDs of the last set of jobs started by this schedule.
        '''
        return tuple(self.__lastJobIds)

    @property
    def owner(self) -> Optional[str]:
        """The owner of this schedule, or None if it does not have an owner."""
        return cast(Optional[str], self._properties.get('owner'))

    @property
    def comment(self) -> str:
        """Gets user-specified comment string for this schedule.
        Comment string may contain newlines.
        """
        return self.__comment

    @property
    def repeat(self) -> ScheduleRepeat:
        """How often should this schedule fire?"""
        return cast(ScheduleRepeat, self._properties['repeat'])

    @property
    def dayFlags(self) -> str:
        """A string of length 7, on position per day, starting at Monday:
        if '0' the schedule does not fire on that day, if '1' it does.
        """
        repeat = self.repeat
        if repeat is ScheduleRepeat.WEEKLY:
            dayFlags = cast(str, self._properties['days'])
            assert '1' in dayFlags and len(dayFlags) == 7, dayFlags
            return dayFlags
        elif repeat is ScheduleRepeat.DAILY:
            return '1' * 7
        else:
            raise ValueError(
                f'dayFlags is not defined for repeat {repeat.name}'
                )

    @property
    def startTime(self) -> int:
        """Returns the start time for this schedule (in seconds since the
        epoch), or `asap` if the schedule will start as soon as possible,
        or `endOfTime` if the schedule has finished and won't start again.
        """
        startTime = self._properties.get('startTime')
        if startTime is None:
            return endOfTime if self.isDone() else asap
        else:
            return cast(int, startTime)

    @property
    def minDelay(self) -> int:
        """The minimum delay between instantiating a continuous schedule,
        in minutes.
        """
        return cast(int, self._properties['minDelay'])

    @property
    def configId(self) -> Optional[str]:
        """The ID of the configuration instantiated by this schedule,
        or None if this schedule picks configurations based on tags instead.
        """
        return cast(Optional[str], self._properties.get('configId'))

    @property
    def tagKey(self) -> str:
        """The tag key for configurations started by this schedule.
        Raises KeyError if this schedule identifies a configuration by
        name instead of by tag.
        TODO: We could have a reserved tag key for the configuration name
              and always use the tagging mechanism.
        """
        return cast(str, self._properties['tagKey'])

    @property
    def tagValue(self) -> str:
        """The tag value for configurations started by this schedule.
        Raises KeyError if this schedule identifies a configuration by
        name instead of by tag.
        """
        return cast(str, self._properties['tagValue'])

    def isBlocked(self) -> bool:
        '''Return True iff this schedule cannot be triggered in its current
        state. Note that triggering is different from running: for example
        a daily schedule can be triggered when suspended, in that case it will
        skip one day.
        '''
        repeat = self.repeat
        if repeat is ScheduleRepeat.ONCE:
            return self.isDone() or self.isSuspended()
        elif repeat is ScheduleRepeat.CONTINUOUSLY:
            return self.isRunning() or self.isSuspended()
        elif repeat is ScheduleRepeat.TRIGGERED:
            return not self._properties['trigger'] or self.isRunning() \
                or self.isSuspended()
        else:
            return False

    def isDone(self) -> bool:
        '''Returns True iff this schedule will not run again.
        '''
        return cast(bool, self._properties.get('done', False))

    def isSuspended(self) -> bool:
        '''Returns True iff this schedule is suspended.
        '''
        return cast(bool, self._properties['suspended'])

    def isRunning(self) -> bool:
        '''Returns True iff one or more of the jobs last instantiated by this
        schedule are not finished yet.
        '''
        return self.__running

    def setSuspend(self, suspended: bool) -> None:
        '''Suspends or resumes a schedule.
        '''
        if self._properties['suspended'] != suspended:
            self._properties['suspended'] = suspended
            self._notify()

    def setTrigger(self) -> None:
        '''Sets the trigger on a triggered schedule.
        Raises ValueError if this is not a triggered schedule.
        '''
        if self.repeat is not ScheduleRepeat.TRIGGERED:
            raise ValueError('Not a triggered schedule')
        if not self._properties['trigger']:
            self._properties['trigger'] = True
            self._notify()

    @property
    def lastRunTime(self) -> Optional[int]:
        """The last time this schedule started jobs,
        or None if the schedule never ran.
        """
        return cast(Optional[int], self._properties.get('lastRunTime'))

    def __adjustStartTime(self,
                          skipToNext: bool,
                          currentTime: Optional[int] = None
                          ) -> None:
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
        startTime = cast(Optional[int], self._properties.get('startTime'))
        repeat = self.repeat

        if startTime is None:
            # Start time can be None if a schedule is done or should start ASAP.
            assert repeat not in (ScheduleRepeat.DAILY, ScheduleRepeat.WEEKLY)

            if not skipToNext:
                # There is nothing to adjust.
                return
            # For continuous schedules started ASAP, it is essential to compute
            # the next start time because of the minimum delay feature.

        elif currentTime < startTime:
            # In theory forced skip and future start time would be possible,
            # but we have no use for it and therefore don't support it.
            assert not skipToNext

            if repeat is not ScheduleRepeat.WEEKLY:
                # Any start time in the future is fine as-is.
                return

        if repeat is ScheduleRepeat.ONCE:
            nextTime = None
        elif repeat is ScheduleRepeat.CONTINUOUSLY:
            assert startTime is None or currentTime >= startTime
            if skipToNext:
                nextTime = ( # round up to minute boundary
                    (currentTime + 59) // 60 + self.minDelay
                    ) * 60
            else:
                nextTime = None
        elif repeat is ScheduleRepeat.TRIGGERED:
            nextTime = None
        else:
            nextTimeList = list(time.localtime(startTime)[:9])
            nextTimeList[8] = -1 # local time: no time zone
            if startTime is None or currentTime >= startTime:
                # Set day to today.
                nextTimeList[:3] = time.localtime(currentTime)[:3]
                if skipToNext:
                    # Move ahead at least one day.
                    nextTimeList[2] += 1
            nextTime = _listToTimestamp(nextTimeList)
            dayFlags = self.dayFlags
            while nextTime < currentTime \
               or dayFlags[time.localtime(nextTime)[6]] != '1':
                nextTimeList[2] += 1
                nextTime = _listToTimestamp(nextTimeList)
        if nextTime is None:
            self._properties.pop('startTime', None)
        else:
            self._properties['startTime'] = nextTime

    def getMatchingConfigIds(self, configDB: ConfigDB) -> Sequence[str]:
        '''Returns the IDs of configurations that will be instantiated by this
        schedule, if the schedule would be triggered right now.
        '''
        configId = self.configId
        if configId is None:
            return tuple(
                config.getId()
                for config in configDB.iterConfigsByTag(self.tagKey,
                                                        self.tagValue)
                )
        else:
            if configId in configDB:
                return (configId,)
            else:
                # Nowadays we no longer allow deletion of the config a schedule
                # refers to it, but there may be old databases in which there
                # are schedules that point to non-existing configs.
                return ()

    def trigger(self, currentTime: int, jobIds: Sequence[str]) -> None:
        """Record the jobs started now and advance the schedule's
        start time for the next run.
        """

        # Update "last run" info.
        self._properties['lastRunTime'] = currentTime
        self.__lastJobIds = jobIds
        self.__running = bool(jobIds)

        # Advance time for next run.
        # To avoid an infinite loop in ScheduleManager, each invocation of
        # trigger() should either increase the schedule's start time or
        # cause isBlocked() to return False (which will lead to the schedule
        # being removed from the heap).
        self.__adjustStartTime(True, currentTime)
        if not self.isSuspended():
            repeat = self.repeat
            if repeat is ScheduleRepeat.ONCE:
                self._properties['done'] = True
            elif repeat is ScheduleRepeat.TRIGGERED:
                self._properties['trigger'] = False

        self._notify()

    def createJobs(self, configDB: ConfigDB, jobDB: JobDB) -> Iterator[str]:
        """Create a job from each matched configuration.
        Yield the IDs of the created jobs.
        """

        for configId in self.getMatchingConfigIds(configDB):
            try:
                config = configDB[configId]
                if config.hasValidInputs():
                    for job in config.createJobs(self.owner):
                        job.comment += '\n' + self.comment
                        job.setScheduledBy(self.getId())
                        jobDB.add(job)
                        yield job.getId()
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

    def _getContent(self) -> XMLContent:
        yield xml.comment[ self.__comment ]
        for jobId in self.__lastJobIds:
            yield xml.job(jobId = jobId)
        yield self.tags.toXML()

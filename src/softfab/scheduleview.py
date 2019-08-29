# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterable, List

from softfab.config import rootURL
from softfab.configlib import configDB
from softfab.joblib import jobDB
from softfab.pagelinks import createJobsURL
from softfab.resultcode import combineResults
from softfab.schedulelib import (
    JobDBObserver, ScheduleRepeat, Scheduled, asap, scheduleDB
)
from softfab.schedulerefs import createScheduleDetailsURL
from softfab.statuslib import (
    DBStatusModelGroup, StatusModel, StatusModelRegistry
)
from softfab.timeview import formatTime
from softfab.webgui import maybeLink
from softfab.xmlgen import XML, XMLContent, xml

weekDays = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
    'Saturday', 'Sunday'
    ]

# Note: If we make weekDays a parameter, these are generic sublist <-> flags
#       converter functions.
# TODO: In Python 3.6 we could use IntFlag.

def listToStringDays(listDays: Iterable[str]) -> str:
    '''Returns a list of days into a 7 characters string
    representative of a week.
    Example: ['Tuesday', 'Thursday'] will be converted into "0101000"
    '''
    return ''.join( str(int(day in listDays)) for day in weekDays )

def stringToListDays(binDays: str) -> List[str]:
    '''Returns a list of days on which a configuration
    should be scheduled in case of a weekly sequence.
    Example: "0101000" will be converted into ['Tuesday', 'Thursday']
    '''
    assert len(binDays) == 0 or len(binDays) == 7
    for flag in binDays:
        assert flag in ('0', '1')
    return [
        weekDay
        for flag, weekDay in zip(binDays, weekDays)
        if int(flag)
        ]

def createLastJobLink(schedule: Scheduled) -> XML:
    return maybeLink(createJobsURL(schedule.getLastJobs()))[
        formatTime(schedule.getLastStartTime())
        ]

def describeNextRun(schedule: Scheduled) -> XMLContent:
    '''Returns a description of when the schedule is next expected to run.
    '''

    # A "once" schedule that is finished never runs again.
    if schedule.isDone():
        return 'done'

    # Compute some useful predicates.
    sequence = schedule['sequence']
    waiting = sequence in (
        ScheduleRepeat.CONTINUOUSLY, ScheduleRepeat.TRIGGERED
        ) and schedule.isRunning()
    suspended = schedule.isSuspended()

    # Look for future start time.
    startTime = schedule.startTime
    if startTime != asap:
        return (
            ('\u2265 ' if waiting or suspended else '= ') # ">=" or "="
            + formatTime(startTime)
            )

    # Schedule should start ASAP; tell user why it hasn't started yet.
    if sequence is ScheduleRepeat.TRIGGERED and not schedule['trigger']:
        return 'not triggered'
    if waiting:
        return 'waiting for last run to finish'

    # Suspend is checked last to be consistent with getScheduleStatus().
    if suspended:
        return 'suspended'

    # We are out of reasons.
    # This can happen between a schedule becoming ready to start and
    # the ScheduleManager actually starting it, but because that time
    # is really short, it is unlikely the user will see this value.
    return 'now'

def getScheduleStatus(schedule: Scheduled) -> str:
    '''Returns the status of the given schedule.
    The familiar color coding is used:
    'done' (gray) means: job will not run anymore
    'running' (blue) means: (continuous) schedule is running
    'suspended' (gray) means: schedule is suspended
    'error' (red) means: one or more matching configs is inconsistent
    'warning' (orange) means: no configurations match the tag
    'ok' (green) means: everything is correct
    '''
    if schedule.isRunning():
        return 'running'
    if schedule.isDone():
        return 'done'
    configIds = schedule.getMatchingConfigIds()
    if not configIds:
        return 'warning'
    for configId in configIds:
        if not configDB[configId].hasValidInputs():
            return 'error'
    if schedule.isSuspended():
        return 'suspended'
    else:
        return 'ok'

class ScheduleModel(StatusModel):

    @classmethod
    def getChildClass(cls):
        return None

    def __init__(self, modelId, parent):
        #print 'create model:', modelId
        if modelId not in scheduleDB:
            raise KeyError('There is no schedule named "%s"' % modelId)
        #print 'create model - found'
        StatusModel.__init__(self, modelId, parent)
        #print 'create model - done'

    def jobUpdated(self, job, schedule):
        assert schedule.getId() == self.getId()
        if job.getId() in schedule.getLastJobs():
            self._notify()

    def scheduleUpdated(self, schedule):
        assert schedule.getId() == self.getId()
        self._notify()

    def _registerForUpdates(self):
        pass

    def _unregisterForUpdates(self):
        pass

    def formatStatus(self):
        scheduleId = self.getId()
        schedule = scheduleDB[scheduleId]
        lastJobs = schedule.getLastJobs()
        result = combineResults(jobDB[jobId] for jobId in lastJobs)
        url = createJobsURL(lastJobs) or createScheduleDetailsURL(scheduleId)
        return xml.status(
            health = result or 'unknown',
            busy = 'true' if schedule.isRunning() else 'false',
            suspended = 'true' if schedule.isSuspended() else 'false',
            url = rootURL + url,
            )

class ScheduleModelGroup(DBStatusModelGroup):
    childClass = ScheduleModel
    db = scheduleDB

    def __init__(self, modelId, parent):
        DBStatusModelGroup.__init__(self, modelId, parent)
        JobDBObserver.instance.addObserver(self.__jobUpdated)

    def __jobUpdated(self, job, schedule):
        child = self._children.get(schedule.getId())
        if child is not None:
            child.jobUpdated(job, schedule)

    def _monitoredRecordUpdated(self, model, record):
        model.scheduleUpdated(record)

StatusModelRegistry.instance.addModelGroup(
    ScheduleModelGroup, 'scheduled jobs'
    )

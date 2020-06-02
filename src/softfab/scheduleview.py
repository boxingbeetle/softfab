# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterable, List

from softfab.configlib import ConfigDB
from softfab.pagelinks import createJobsURL
from softfab.schedulelib import ScheduleRepeat, Scheduled, asap
from softfab.timeview import formatTime
from softfab.webgui import maybeLink
from softfab.xmlgen import XML, XMLContent

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
    should be scheduled in case of a weekly repeat.
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
    repeat = schedule.repeat
    waiting = repeat in (
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
    if repeat is ScheduleRepeat.TRIGGERED and not schedule['trigger']:
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

def getScheduleStatus(configDB: ConfigDB, schedule: Scheduled) -> str:
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
    configIds = schedule.getMatchingConfigIds(configDB)
    if not configIds:
        return 'warning'
    for configId in configIds:
        if not configDB[configId].hasValidInputs():
            return 'error'
    if schedule.isSuspended():
        return 'suspended'
    else:
        return 'ok'

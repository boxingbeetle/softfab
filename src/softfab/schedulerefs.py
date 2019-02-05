# SPDX-License-Identifier: BSD-3-Clause

from pageargs import PageArgs, StrArg
from webgui import pageLink, pageURL

class ScheduleIdArgs(PageArgs):
    '''Identifies a particular schedule.
    '''
    id = StrArg()

def createScheduleDetailsURL(scheduleId):
    return pageURL('ScheduleDetails', ScheduleIdArgs(id = scheduleId))

def createScheduleDetailsLink(scheduleId):
    return pageLink('ScheduleDetails', ScheduleIdArgs(id = scheduleId))[
        scheduleId
        ]

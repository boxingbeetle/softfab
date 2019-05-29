# SPDX-License-Identifier: BSD-3-Clause

from softfab.pageargs import PageArgs, StrArg
from softfab.webgui import pageLink, pageURL
from softfab.xmlgen import XMLNode


class ScheduleIdArgs(PageArgs):
    '''Identifies a particular schedule.
    '''
    id = StrArg()

def createScheduleDetailsURL(scheduleId: str) -> str:
    return pageURL('ScheduleDetails', ScheduleIdArgs(id = scheduleId))

def createScheduleDetailsLink(scheduleId: str) -> XMLNode:
    return pageLink('ScheduleDetails', ScheduleIdArgs(id = scheduleId))[
        scheduleId
        ]

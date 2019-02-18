# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, Redirect
from softfab.config import enableSecurity
from softfab.datawidgets import DataColumn, DataTable, LinkColumn
from softfab.formlib import makeForm
from softfab.pageargs import DictArg, EnumArg, IntArg, PageArgs, SortArg
from softfab.schedulelib import scheduleDB
from softfab.schedulerefs import createScheduleDetailsLink
from softfab.scheduleview import (
    createLastJobLink, describeNextRun, getScheduleStatus
    )
from softfab.userview import OwnerColumn
from softfab.webgui import pageLink, pageURL
from softfab.xmlgen import xhtml

from enum import Enum

class NameColumn(DataColumn):
    label = 'Name'
    keyName = 'id'
    def presentCell(self, record, **kwargs):
        return createScheduleDetailsLink(record.getId())

class LastRunColumn(DataColumn):
    label = 'Last Run'
    keyName = 'lastStartTime'
    cellStyle = 'nobreak'
    def presentCell(self, record, **kwargs):
        return createLastJobLink(record)

class NextRunColumn(DataColumn):
    label = 'Next Run'
    keyName = 'startTime'
    cellStyle = 'nobreak'
    def presentCell(self, record, **kwargs):
        return describeNextRun(record)

class SequenceColumn(DataColumn):
    label = 'Sequence'
    keyName = 'sequence'
    @staticmethod
    def sortKey(record):
        return record['sequence'].name

class SuspendColumn(DataColumn):
    label = 'Action'
    def presentCell(self, record, **kwargs):
        if record.isDone():
            return None
        else:
            suspend = not record.isSuspended()
            return xhtml.button(
                name = 'action.%s' % record.getId(), type = 'submit',
                value = Actions.SUSPEND if suspend else Actions.RESUME
                )[ 'Suspend' if suspend else 'Resume' ]

class ScheduleTable(DataTable):
    widgetId = 'scheduleTable'
    autoUpdate = True
    db = scheduleDB

    def iterRowStyles(self, rowNr, record, **kwargs):
        yield getScheduleStatus(record)

    def iterColumns(self, **kwargs):
        yield NameColumn.instance
        yield LastRunColumn.instance
        yield NextRunColumn.instance
        yield SequenceColumn.instance
        if enableSecurity:
            yield OwnerColumn.instance
        yield LinkColumn('Edit', 'ScheduleEdit')
        yield LinkColumn('Delete', 'DelSchedule')
        yield SuspendColumn.instance

Actions = Enum('Actions', 'SUSPEND RESUME')

class ScheduleIndex_GET(FabPage):
    icon = 'IconSchedule'
    description = 'Schedules'
    children = [
        'ScheduleEdit', 'ScheduleDetails',
        'DelSchedule', 'DelFinishedSchedules',
        ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):

        def process(self, req):
            self.finishedSchedules = any(
                schedule.isDone() for schedule in scheduleDB
                )


    def checkAccess(self, req):
        req.checkPrivilege('s/l')

    def iterDataTables(self, proc):
        yield ScheduleTable.instance

    def iterWidgets(self, proc):
        yield ScheduleTable

    def presentContent(self, proc):
        yield makeForm(args=proc.args)[
            ScheduleTable.instance
            ].present(proc=proc)
        if proc.finishedSchedules:
            yield xhtml.p[
                pageLink('DelFinishedSchedules')[
                    'Delete all finished schedules'
                    ]
                ]

class ScheduleIndex_POST(FabPage):
    icon = 'IconSchedule'
    description = 'Schedules'

    class Arguments(ScheduleIndex_GET.Arguments):
        action = DictArg(EnumArg(Actions))

    class Processor(PageProcessor):

        def process(self, req):
            for scheduleId, action in req.args.action.items():
                # Toggle suspend.
                scheduled = scheduleDB.get(scheduleId)
                # TODO: Report when action is not possible, instead of ignoring.
                if scheduled is not None:
                    req.checkPrivilegeForOwned(
                        's/m', scheduled, (
                            'suspend/resume this schedule',
                            'suspend/resume schedules'
                            )
                        )
                    if not scheduled.isDone():
                        scheduled.setSuspend(action is Actions.SUSPEND)
            raise Redirect(pageURL(
                'ScheduleIndex',
                ScheduleIndex_GET.Arguments.subset(req.args)
                ))

    def checkAccess(self, req):
        pass # Processor checks privs.

    def presentContent(self, proc):
        assert False
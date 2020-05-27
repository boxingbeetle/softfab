# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import ClassVar, Iterator, Mapping, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, Redirect
from softfab.configlib import ConfigDB
from softfab.datawidgets import DataColumn, DataTable, LinkColumn
from softfab.formlib import makeForm
from softfab.pageargs import DictArg, EnumArg, IntArg, PageArgs, SortArg
from softfab.request import Request
from softfab.schedulelib import ScheduleDB, Scheduled, scheduleDB
from softfab.schedulerefs import createScheduleDetailsLink
from softfab.scheduleview import (
    createLastJobLink, describeNextRun, getScheduleStatus
)
from softfab.userlib import (
    User, UserDB, checkPrivilege, checkPrivilegeForOwned
)
from softfab.userview import OwnerColumn
from softfab.webgui import Widget, pageLink, pageURL
from softfab.xmlgen import XMLContent, xhtml


class NameColumn(DataColumn[Scheduled]):
    label = 'Name'
    keyName = 'id'

    def presentCell(self, record: Scheduled, **kwargs: object) -> XMLContent:
        return createScheduleDetailsLink(record.getId())

class LastRunColumn(DataColumn[Scheduled]):
    label = 'Last Run'
    keyName = 'lastStartTime'
    cellStyle = 'nobreak'

    def presentCell(self, record: Scheduled, **kwargs: object) -> XMLContent:
        return createLastJobLink(record)

class NextRunColumn(DataColumn[Scheduled]):
    label = 'Next Run'
    keyName = 'startTime'
    cellStyle = 'nobreak'

    def presentCell(self, record: Scheduled, **kwargs: object) -> XMLContent:
        return describeNextRun(record)

class RepeatColumn(DataColumn[Scheduled]):
    label = 'Repeat'
    keyName = 'repeat'

    @staticmethod
    def repeatName(record: Scheduled) -> str:
        return record.repeat.name

    sortKey = repeatName

class SuspendColumn(DataColumn[Scheduled]):
    label = 'Action'

    def presentCell(self, record: Scheduled, **kwargs: object) -> XMLContent:
        if record.isDone():
            return None
        else:
            suspend = not record.isSuspended()
            return xhtml.button(
                name = f'action.{record.getId()}',
                type = 'submit',
                value = Actions.SUSPEND if suspend else Actions.RESUME
                )[ 'Suspend' if suspend else 'Resume' ]

class ScheduleTable(DataTable[Scheduled]):
    widgetId = 'scheduleTable'
    autoUpdate = True
    db = scheduleDB

    def iterRowStyles( # pylint: disable=unused-argument
                      self, rowNr: int, record: Scheduled, **kwargs: object
                      ) -> Iterator[str]:
        proc = cast(ScheduleIndex_GET.Processor, kwargs['proc'])
        yield getScheduleStatus(proc.configDB, record)

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn[Scheduled]]:
        proc = cast(ScheduleIndex_GET.Processor, kwargs['proc'])
        yield NameColumn.instance
        yield LastRunColumn.instance
        yield NextRunColumn.instance
        yield RepeatColumn.instance
        if proc.userDB.showOwners:
            yield OwnerColumn[Scheduled].instance
        yield LinkColumn('Edit', 'ScheduleEdit')
        yield LinkColumn('Delete', 'DelSchedule')
        yield SuspendColumn.instance

Actions = Enum('Actions', 'SUSPEND RESUME')

class ScheduleIndex_GET(FabPage['ScheduleIndex_GET.Processor',
                                'ScheduleIndex_GET.Arguments']):
    icon = 'IconSchedule'
    description = 'Schedules'
    children = [
        'ScheduleEdit', 'ScheduleDetails',
        'DelSchedule', 'DelFinishedSchedules',
        ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor['ScheduleIndex_GET.Arguments']):

        scheduleDB: ClassVar[ScheduleDB]
        configDB: ClassVar[ConfigDB]
        userDB: ClassVar[UserDB]

        async def process(self,
                          req: Request['ScheduleIndex_GET.Arguments'],
                          user: User
                          ) -> None:
            # pylint: disable=attribute-defined-outside-init
            self.finishedSchedules = any(
                schedule.isDone() for schedule in self.scheduleDB
                )

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 's/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield ScheduleTable.instance

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        yield ScheduleTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ScheduleIndex_GET.Processor, kwargs['proc'])
        yield makeForm(args=proc.args)[
            ScheduleTable.instance
            ].present(**kwargs)
        if proc.finishedSchedules:
            yield xhtml.p[
                pageLink('DelFinishedSchedules')[
                    'Delete all finished schedules'
                    ]
                ]

class ScheduleIndex_POST(FabPage['ScheduleIndex_POST.Processor',
                                 'ScheduleIndex_POST.Arguments']):
    icon = 'IconSchedule'
    description = 'Schedules'

    class Arguments(ScheduleIndex_GET.Arguments):
        action = DictArg(EnumArg(Actions))

    class Processor(PageProcessor['ScheduleIndex_POST.Arguments']):

        scheduleDB: ClassVar[ScheduleDB]

        async def process(self,
                          req: Request['ScheduleIndex_POST.Arguments'],
                          user: User
                          ) -> None:
            actions = cast(Mapping[str, str], req.args.action)
            for scheduleId, action in actions.items():
                # Toggle suspend.
                scheduled = self.scheduleDB.get(scheduleId)
                # TODO: Report when action is not possible, instead of ignoring.
                if scheduled is not None:
                    checkPrivilegeForOwned(
                        user, 's/m', scheduled, (
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

    def checkAccess(self, user: User) -> None:
        pass # Processor checks privs.

    def presentContent(self, **kwargs: object) -> XMLContent:
        assert False

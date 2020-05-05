# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import cast

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, ProcT, Redirect
from softfab.formlib import actionButtons, makeForm
from softfab.pageargs import ArgsT, EnumArg, PageArgs
from softfab.request import Request
from softfab.schedulelib import scheduleDB
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import XMLContent, xhtml

Actions = Enum('Actions', 'DELETE CANCEL')

class DelFinishedSchedulesBase(FabPage[ProcT, ArgsT]):
    # Refuse child link from ScheduleIndex.
    linkDescription = False
    description = 'Delete Schedules'
    icon = 'IconSchedule'
    iconModifier = IconModifier.DELETE

    def checkAccess(self, user: User) -> None:
        pass

    def presentContent(self, **kwargs: object) -> XMLContent:
        raise NotImplementedError

class DelFinishedSchedules_GET(
        DelFinishedSchedulesBase[FabPage.Processor,
                                 'DelFinishedSchedules_GET.Arguments']
        ):

    class Arguments(PageArgs):
        pass

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield xhtml.p[ 'Delete all finished schedules?' ]
        yield makeForm()[
            xhtml.p[ actionButtons(Actions) ]
            ].present(**kwargs)

class DelFinishedSchedules_POST(
        DelFinishedSchedulesBase['DelFinishedSchedules_POST.Processor',
                                 'DelFinishedSchedules_POST.Arguments']
        ):

    class Arguments(PageArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor['DelFinishedSchedules_POST.Arguments']):

        async def process(self,
                          req: Request['DelFinishedSchedules_POST.Arguments'],
                          user: User
                          ) -> None:
            action = req.args.action
            if action is Actions.CANCEL:
                page = cast(DelFinishedSchedules_POST, self.page)
                raise Redirect(page.getParentURL(req.args))
            elif action is Actions.DELETE:
                checkPrivilege(user, 's/d', 'delete all finished schedules')
                finishedSchedules = [
                    schedule for schedule in scheduleDB if schedule.isDone()
                    ]
                for schedule in finishedSchedules:
                    scheduleDB.remove(schedule)
            else:
                assert False, action

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(DelFinishedSchedules_POST.Processor, kwargs['proc'])
        yield (
            xhtml.p[ 'All finished schedules have been deleted.' ],
            self.backToParent(proc.args)
            )

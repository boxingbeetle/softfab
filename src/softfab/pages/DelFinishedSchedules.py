# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import ArgT, PageProcessor, ProcT, Redirect
from softfab.formlib import actionButtons, makeForm
from softfab.pageargs import EnumArg, PageArgs
from softfab.schedulelib import scheduleDB
from softfab.userlib import IUser, checkPrivilege
from softfab.xmlgen import XMLContent, xhtml

Actions = Enum('Actions', 'DELETE CANCEL')

class DelFinishedSchedulesBase(FabPage[ProcT, ArgT]):
    # Refuse child link from ScheduleIndex.
    linkDescription = False
    description = 'Delete Schedules'
    icon = 'IconSchedule'
    iconModifier = IconModifier.DELETE

    def checkAccess(self, user: IUser) -> None:
        pass

    def presentContent(self, proc: ProcT):
        raise NotImplementedError

class DelFinishedSchedules_GET(
        DelFinishedSchedulesBase[FabPage.Processor,
                                 'DelFinishedSchedules_GET.Arguments']
        ):

    class Arguments(PageArgs):
        pass

    def presentContent(self, proc: FabPage.Processor) -> XMLContent:
        yield xhtml.p[ 'Delete all finished schedules?' ]
        yield makeForm()[
            xhtml.p[ actionButtons(Actions) ]
            ].present(proc=proc)

class DelFinishedSchedules_POST(
        DelFinishedSchedulesBase['DelFinishedSchedules_POST.Processor',
                                 'DelFinishedSchedules_POST.Arguments']
        ):

    class Arguments(PageArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor):

        def process(self, req):
            action = req.args.action
            if action is Actions.CANCEL:
                raise Redirect(self.page.getParentURL(req))
            elif action is Actions.DELETE:
                checkPrivilege(req.user, 's/d', 'delete all finished schedules')
                finishedSchedules = [
                    schedule for schedule in scheduleDB if schedule.isDone()
                    ]
                for schedule in finishedSchedules:
                    scheduleDB.remove(schedule)
            else:
                assert False, action

    def presentContent(self, proc: Processor) -> XMLContent:
        yield (
            xhtml.p[ 'All finished schedules have been deleted.' ],
            self.backToParent(proc.req)
            )

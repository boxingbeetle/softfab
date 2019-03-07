# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, Redirect
from softfab.formlib import actionButtons, makeForm
from softfab.pageargs import EnumArg, PageArgs
from softfab.schedulelib import scheduleDB
from softfab.xmlgen import xhtml

from enum import Enum

Actions = Enum('Actions', 'DELETE CANCEL')

class DelFinishedSchedules_GET(FabPage):
    # Refuse child link from ScheduleIndex.
    linkDescription = False
    description = 'Delete Schedules'
    icon = 'IconSchedule'
    iconModifier = IconModifier.DELETE

    class Arguments(PageArgs):
        pass

    def checkAccess(self, req):
        pass

    def presentContent(self, proc):
        yield xhtml.p[ 'Delete all finished schedules?' ]
        yield makeForm()[
            xhtml.p[ actionButtons(Actions) ]
            ].present(proc=proc)

class DelFinishedSchedules_POST(DelFinishedSchedules_GET):

    class Arguments(PageArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor):

        def process(self, req):
            action = req.args.action
            if action is Actions.CANCEL:
                raise Redirect(self.page.getParentURL(req))
            elif action is Actions.DELETE:
                req.checkPrivilege('s/d', 'delete all finished schedules')
                finishedSchedules = [
                    schedule for schedule in scheduleDB if schedule.isDone()
                    ]
                for schedule in finishedSchedules:
                    scheduleDB.remove(schedule)
            else:
                assert False, action

    def presentContent(self, proc):
        yield (
            xhtml.p[ 'All finished schedules have been deleted.' ],
            self.backToParent(proc.req)
            )

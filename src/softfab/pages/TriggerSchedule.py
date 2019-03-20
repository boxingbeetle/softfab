# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.pageargs import PageArgs, StrArg
from softfab.schedulelib import scheduleDB
from softfab.userlib import User, checkPrivilege, checkPrivilegeForOwned
from softfab.xmlgen import xml


class TriggerSchedule_POST(ControlPage['TriggerSchedule_POST.Arguments', 'TriggerSchedule_POST.Processor']):

    class Arguments(PageArgs):
        scheduleId = StrArg()

    class Processor(PageProcessor):

        def process(self, req):
            scheduleId = req.args.scheduleId
            try:
                schedule = scheduleDB[scheduleId]
            except KeyError:
                raise InvalidRequest(
                    'Schedule "%s" does not exist' % scheduleId
                    )
            checkPrivilegeForOwned(
                req.user, 's/m', schedule,
                ( 'trigger schedule "%s" that is not owned by you' % scheduleId,
                  'trigger schedules' )
                )
            try:
                schedule.setTrigger()
            except ValueError as ex:
                raise InvalidRequest( str(ex) )

    def checkAccess(self, user: User) -> None:
        # Error messages might leak info about schedule, so make sure at least
        # read-only access is allowed.
        # The processor will do additional checks.
        checkPrivilege(user, 's/a')

    def writeReply(self, response, proc):
        response.write(xml.ok)

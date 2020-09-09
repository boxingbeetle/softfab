# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.jobview import alertList
from softfab.pageargs import StrArg
from softfab.pagelinks import TaskIdArgs
from softfab.request import Request
from softfab.response import Response
from softfab.tasktables import TaskProcessorMixin
from softfab.users import User, checkPrivilege
from softfab.xmlgen import xml


class TaskAlert_POST(ControlPage['TaskAlert_POST.Arguments',
                                 'TaskAlert_POST.Processor']):

    class Arguments(TaskIdArgs):
        alert = StrArg()

    class Processor(TaskProcessorMixin,
                    PageProcessor['TaskAlert_POST.Arguments']):

        async def process(self,
                          req: Request['TaskAlert_POST.Arguments'],
                          user: User
                          ) -> None:
            self.initTask(req)

            alert = req.args.alert
            if alert != '' and alert not in alertList:
                raise InvalidRequest(f'Invalid alert status "{alert}"')

            self.task.setAlert(alert)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 't/m', 'set alert status')

    async def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.ok)

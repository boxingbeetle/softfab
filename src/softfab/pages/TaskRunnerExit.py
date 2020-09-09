# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.pagelinks import TaskRunnerIdArgs
from softfab.request import Request
from softfab.resourcelib import ResourceDB
from softfab.response import Response
from softfab.users import User, checkPrivilege
from softfab.xmlgen import xml


class TaskRunnerExit_POST(ControlPage['TaskRunnerExit_POST.Arguments',
                                      'TaskRunnerExit_POST.Processor']):

    class Arguments(TaskRunnerIdArgs):
        pass

    class Processor(PageProcessor[TaskRunnerIdArgs]):

        resourceDB: ClassVar[ResourceDB]

        async def process(self,
                          req: Request[TaskRunnerIdArgs],
                          user: User
                          ) -> None:
            runnerId = req.args.runnerId
            try:
                runner = self.resourceDB.getTaskRunner(runnerId)
            except KeyError as ex:
                raise InvalidRequest(str(ex)) from ex
            runner.setExitFlag(True)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'r/m', 'control resources')

    async def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.ok)
        # TODO: Write error body in addition to result code.
        #response.writeXML(xml.error(message = error))

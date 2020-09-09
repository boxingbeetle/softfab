# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Mapping, cast

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.pageargs import DictArg, EnumArg, StrArg
from softfab.pagelinks import TaskIdArgs
from softfab.request import Request
from softfab.response import Response
from softfab.resultcode import ResultCode
from softfab.resultlib import ResultStorage
from softfab.tasktables import TaskProcessorMixin
from softfab.users import User, checkPrivilege, checkPrivilegeForOwned
from softfab.xmlgen import xml


class InspectDone_POST(ControlPage['InspectDone_POST.Arguments',
                                   'InspectDone_POST.Processor']):

    class Arguments(TaskIdArgs):
        result = EnumArg(ResultCode)
        summary = StrArg(None)
        data = DictArg(StrArg())

    class Processor(TaskProcessorMixin,
                    PageProcessor['InspectDone_POST.Arguments']):

        resultStorage: ClassVar[ResultStorage]

        async def process(self,
                          req: Request['InspectDone_POST.Arguments'],
                          user: User
                          ) -> None:
            # Fetch and check job and task.
            self.initTask(req)
            job = self.job
            task = self.task
            taskName = task.getName()
            taskRun = task.getLatestRun()
            if not taskRun.isWaitingForInspection():
                raise InvalidRequest(
                    'Given task is not waiting for inspection'
                    )

            # Check result and summary.
            result = req.args.result
            if result not in (
                ResultCode.OK, ResultCode.WARNING, ResultCode.ERROR
                ):
                raise InvalidRequest(f'Invalid inspection result "{result}"')
            summary = req.args.summary

            # Check store permissions.
            checkPrivilegeForOwned(user, 't/m', job)

            # Store mid-level data, if any.
            data = cast(Mapping[str, str], req.args.data)
            if data:
                self.resultStorage.putData(taskName, taskRun.getId(), data)

            # Store inspection result.
            job.inspectDone(taskName, result, summary)

    def checkAccess(self, user: User) -> None:
        # Error messages might leak info about job/task existence, so make sure
        # at least read-only access is allowed.
        # The processor will do additional checks.
        checkPrivilege(user, 'j/l')
        checkPrivilege(user, 't/l')

    async def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.ok)

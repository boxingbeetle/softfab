# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Mapping, cast
import logging

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.authentication import TokenAuthPage
from softfab.joblib import JobDB
from softfab.pageargs import DictArg, EnumArg, ListArg, PageArgs, StrArg
from softfab.request import Request
from softfab.resourcelib import ResourceDB
from softfab.response import Response
from softfab.resultcode import ResultCode
from softfab.resultlib import ResultStorage
from softfab.taskrunlib import defaultSummaries
from softfab.tokens import TokenRole, TokenUser
from softfab.users import User, checkPrivilege
from softfab.xmlgen import xml


class TaskDone_POST(ControlPage['TaskDone_POST.Arguments',
                                'TaskDone_POST.Processor']):
    authenticator = TokenAuthPage(TokenRole.RESOURCE)

    class Arguments(PageArgs):
        result = EnumArg(ResultCode, None)
        summary = StrArg(None)
        report = ListArg()
        id = StrArg()
        name = StrArg()
        output = DictArg(StrArg())
        data = DictArg(StrArg())

    class Processor(PageProcessor['TaskDone_POST.Arguments']):

        jobDB: ClassVar[JobDB]
        resourceDB: ClassVar[ResourceDB]
        resultStorage: ClassVar[ResultStorage]

        async def process(self,
                          req: Request['TaskDone_POST.Arguments'],
                          user: User
                          ) -> None:
            # Verify arguments.
            try:
                result = req.args.result
                if result is not None and result not in defaultSummaries:
                    raise InvalidRequest(
                        f'Result code "{result}" is for internal use only'
                        )
                summary = req.args.summary
                reports = req.args.report
                outputs = cast(Mapping[str, str], req.args.output)

                # Find Task Runner.
                assert isinstance(user, TokenUser), user
                try:
                    taskRunner = self.resourceDB.runnerFromToken(user)
                except KeyError as ex:
                    raise InvalidRequest(*ex.args) from ex

                jobId = req.args.id
                runningTask = taskRunner.getRun()
                if runningTask is None:
                    raise InvalidRequest(
                        f'Task Runner "{taskRunner.getId()}" '
                        f'is not running a task'
                        )
                try:
                    job = self.jobDB[jobId]
                except KeyError:
                    raise InvalidRequest(
                        f'No job exists with ID "{jobId}"'
                        )
                taskName = req.args.name
                task = job.getTask(taskName)
                if task is None:
                    raise InvalidRequest(
                        f'No task "{taskName}" in job "{jobId}"'
                        )
                runId = cast(str, task['run'])
                if runningTask.getId() != runId:
                    raise InvalidRequest(
                        f'Task Runner "{taskRunner.getId()}" '
                        f'is running task {runningTask.getId()} '
                        f'but wants to set {runId} as done'
                        )

                for report in reports:
                    # Reject anything that looks like a path separator.
                    for tabooChar in ('/', '\\', ':'):
                        if tabooChar in report:
                            raise InvalidRequest(
                                f'Invalid character "{tabooChar}" in '
                                f'report name "{report}"'
                                )

                extracted = cast(Mapping[str, str], req.args.data)

            except InvalidRequest as ex:
                logging.warning('Invalid TaskDone request: %s', ex)
                raise

            # Start making changes.
            if extracted:
                self.resultStorage.putData(taskName, runId, extracted)
            job.taskDone(taskName, result, summary, reports, outputs)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'tr/*', 'set tasks results')

    async def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.ok)

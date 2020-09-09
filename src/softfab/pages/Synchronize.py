# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Optional, cast

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.authentication import TokenAuthPage
from softfab.joblib import JobDB, UnfinishedJobs
from softfab.request import Request
from softfab.resourcelib import (
    RequestFactory, ResourceDB, TaskRunner, TaskRunnerData
)
from softfab.response import Response
from softfab.taskrunlib import TaskRun
from softfab.tokens import TokenRole, TokenUser
from softfab.users import User, checkPrivilege
from softfab.xmlbind import parse
from softfab.xmlgen import XMLContent, xml


def assignExecutionRun(taskRunner: TaskRunner,
                       unfinishedJobs: UnfinishedJobs
                       ) -> Optional[TaskRun]:
    # Find oldest unassigned task.
    capabilities = taskRunner.capabilities
    # TODO: It would be more efficient to keep non-fixed tasks instead of
    #       jobs, but the code for that would be more complex.
    for job in unfinishedJobs:
        # Note that we will accept capabilities that were targets earlier
        # but are no longer marked as targets. This is deliberate, to match
        # the "reason for waiting" logic.
        target = job.getTarget()
        if target is None or target in capabilities:
            # Try to assign this job, might fail for various
            # reasons, such as:
            # - all tasks done
            # - dependencies not ready yet
            # - not enough resources are available
            # - capabilities do not match
            newRun = job.assignTask(taskRunner)
            if newRun:
                return newRun
    return None

class Synchronize_POST(ControlPage[ControlPage.Arguments,
                                   'Synchronize_POST.Processor']):
    authenticator = TokenAuthPage(TokenRole.RESOURCE)

    class Processor(PageProcessor[ControlPage.Arguments]):

        resourceDB: ClassVar[ResourceDB]
        jobDB: ClassVar[JobDB]
        unfinishedJobs: ClassVar[UnfinishedJobs]

        async def process(self,
                          req: Request[ControlPage.Arguments],
                          user: User
                          ) -> None:
            # pylint: disable=attribute-defined-outside-init

            # Parse posted XML request.
            rawReq = req.rawInput()
            request = cast(TaskRunnerData, parse(RequestFactory(), rawReq))

            # Sync Task Runner database.
            assert isinstance(user, TokenUser), user
            try:
                taskRunner = self.resourceDB.runnerFromToken(user)
            except KeyError as ex:
                raise InvalidRequest(*ex.args) from ex
            self.taskRunner = taskRunner
            self.abort = taskRunner.sync(self.jobDB, request)

            # Try to assign a new run if the Task Runner is available.
            # Or exit if the Task Runner exit flag is set.
            self.exit = False
            self.newRun = None
            if not taskRunner.isReserved():
                if taskRunner.shouldExit():
                    self.exit = True
                    taskRunner.setExitFlag(False)
                elif not taskRunner.isSuspended():
                    self.newRun = assignExecutionRun(taskRunner,
                                                     self.unfinishedJobs)

        def createResponse(self) -> XMLContent:
            taskRunner = self.taskRunner
            resourceDB = self.resourceDB
            if self.abort:
                yield xml.abort
            if self.exit:
                yield xml.exit
            else:
                if self.newRun:
                    yield self.newRun.externalize(resourceDB)
                    waitSecs = taskRunner.getMinimalDelay()
                else:
                    waitSecs = taskRunner.getSyncWaitDelay()
                yield xml.wait(seconds = waitSecs)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'tr/*', 'sync a Task Runner')

    async def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.response[proc.createResponse()])

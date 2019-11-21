# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.authentication import TokenAuthPage
from softfab.jobview import unfinishedJobs
from softfab.resourcelib import RequestFactory, resourceDB, runnerFromToken
from softfab.response import Response
from softfab.tokens import TokenRole, TokenUser
from softfab.userlib import User, checkPrivilege
from softfab.xmlbind import parse
from softfab.xmlgen import XMLContent, xml


class Synchronize_POST(ControlPage[ControlPage.Arguments,
                                   'Synchronize_POST.Processor']):
    authenticator = TokenAuthPage(TokenRole.RESOURCE)

    def assignExecutionRun(self, taskRunner):
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

    class Processor(PageProcessor[ControlPage.Arguments]):

        def process(self, req, user):
            # pylint: disable=attribute-defined-outside-init

            # Parse posted XML request.
            rawReq = req.rawInput()
            request = parse(RequestFactory(), rawReq)

            # Sync Task Runner database.
            assert isinstance(user, TokenUser), user
            try:
                taskRunner = runnerFromToken(user)
            except KeyError as ex:
                raise InvalidRequest(*ex.args) from ex
            self.taskRunner = taskRunner
            self.abort = taskRunner.sync(request)

            # Try to assign a new run if the Task Runner is available.
            # Or exit if the Task Runner exit flag is set.
            self.exit = False
            self.newRun = None
            if not taskRunner.isReserved():
                if taskRunner.shouldExit():
                    self.exit = True
                    taskRunner.setExitFlag(False)
                elif not taskRunner.isSuspended():
                    self.newRun = self.page.assignExecutionRun(taskRunner)

        def createResponse(self) -> XMLContent:
            taskRunner = self.taskRunner
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

    def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.response[proc.createResponse()])

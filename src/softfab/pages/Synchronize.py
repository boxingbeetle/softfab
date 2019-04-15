# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import PageProcessor
from softfab.authentication import NoAuthPage
from softfab.jobview import unfinishedJobs
from softfab.resourcelib import (
    RequestFactory, TaskRunner, resourceDB, taskRunnerDB
)
from softfab.response import Response
from softfab.shadowlib import shadowDB
from softfab.sortedqueue import SortedQueue
from softfab.userlib import User
from softfab.xmlbind import parse
from softfab.xmlgen import XMLContent, xml


class WaitingShadowRuns(SortedQueue):
    compareField = 'createtime'

    def _filter(self, record):
        return record.isWaiting()

class Synchronize_POST(ControlPage[ControlPage.Arguments,
                                   'Synchronize_POST.Processor']):
    authenticator = NoAuthPage

    waitingShadowRuns = WaitingShadowRuns(shadowDB)

    def assignShadowRun(self, taskRunner):
        for shadowRun in self.waitingShadowRuns:
            if shadowRun.assign(taskRunner):
                return shadowRun
        return None

    def assignExecutionRun(self, taskRunner):
        # COMPAT 2.x.x: Refuse to assign to 2.x.x Task Runners.
        if taskRunner['version'][0] < 3:
            return None
        # Find oldest unassigned task.
        capabilities = taskRunner.capabilities
        # TODO: It would be more efficient to keep non-fixed tasks instead of
        #       jobs, but the code for that would be more complex.
        for job in unfinishedJobs:
            # Note that we will accept capabilities that were targets earlier
            # but are no longer marked as targets. This is deliberate, to match
            # the "reason for waiting" logic.
            if job['target'] in capabilities:
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
            runnerId = request.getId()
            taskRunner = taskRunnerDB.get(runnerId)
            if taskRunner is None:
                taskRunner = TaskRunner.create(runnerId, '', ())
                taskRunnerDB.add(taskRunner)
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
                    self.newRun = self.page.assignShadowRun(taskRunner) \
                        or self.page.assignExecutionRun(taskRunner)

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
        pass

    def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.response[proc.createResponse()])

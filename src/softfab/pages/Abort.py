# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.joblib import Task, jobDB
from softfab.pageargs import BoolArg, PageArgs, SetArg
from softfab.request import Request
from softfab.response import Response
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml


class Abort_POST(ControlPage['Abort_POST.Arguments', 'Abort_POST.Processor']):

    class Arguments(PageArgs):
        jobId = SetArg()
        taskName = SetArg()
        onlyWaiting = BoolArg()

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 't/m')

    class Processor(PageProcessor['Abort_POST.Arguments']):

        def process(self,
                    req: Request['Abort_POST.Arguments'],
                    user: User
                    ) -> None:
            jobIds = req.args.jobId
            taskNames = req.args.taskName
            onlyWaiting = req.args.onlyWaiting

            # Expect at least 1 jobId
            if not jobIds:
                raise InvalidRequest('No job IDs given; expected at least one')

            # Validate all jobId's
            invalidJobs = [jobId for jobId in jobIds if jobId not in jobDB]
            if invalidJobs:
                raise InvalidRequest(
                    'Non-existing jobs: %s' % ', '.join(sorted(invalidJobs))
                    )

            def checkAbort(task: Task) -> bool:
                if onlyWaiting and not task.isWaiting():
                    return False
                elif taskNames and task.getName() not in taskNames:
                    return False
                else:
                    return True

            userName = user.name
            abortedTasks = {}
            for jobId in jobIds:
                job = jobDB[jobId]
                abortedTasks[jobId] = job.abortAll(checkAbort, userName)

            # pylint: disable=attribute-defined-outside-init
            self.abortedTasks = abortedTasks

    async def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.abortedtasks[(
            xml.taskref(jobid = jobId, taskname = taskName)
            for jobId, taskNames in proc.abortedTasks.items()
            for taskName in taskNames
            )])

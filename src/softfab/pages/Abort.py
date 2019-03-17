# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.joblib import jobDB
from softfab.pageargs import BoolArg, PageArgs, SetArg
from softfab.userlib import IUser, checkPrivilege
from softfab.xmlgen import xml


class Abort_POST(ControlPage['Abort_POST.Arguments', 'Abort_POST.Processor']):

    class Arguments(PageArgs):
        jobId = SetArg()
        taskName = SetArg()
        onlyWaiting = BoolArg()

    def checkAccess(self, user: IUser) -> None:
        checkPrivilege(user, 't/m')

    class Processor(PageProcessor):

        def process(self, req):
            jobIds = req.args.jobId
            taskNames = req.args.taskName
            onlyWaiting = req.args.onlyWaiting

            # Expect at least 1 jobId
            if not jobIds:
                raise InvalidRequest('No jobId\'s given; expected at least one')

            # Validate all jobId's
            invalidJobs = [jobId for jobId in jobIds if jobId not in jobDB]
            if invalidJobs:
                raise InvalidRequest(
                    'Not existing jobs: %s' % ', '.join(sorted(invalidJobs))
                    )

            if onlyWaiting:
                waitingFunc = lambda task: task.isWaiting()
            else:
                waitingFunc = lambda task: True

            if taskNames:
                nameFunc = lambda task: task.getName() in taskNames
            else:
                nameFunc = lambda task: True

            userName = req.userName
            abortedTasks = {}

            for jobId in jobIds:
                abortedTaskNames = jobDB[jobId].abortAll(
                    lambda task: waitingFunc(task) and nameFunc(task),
                    userName
                    )
                abortedTasks[jobId] = abortedTaskNames

            # pylint: disable=attribute-defined-outside-init
            self.abortedTasks = abortedTasks

    def writeReply(self, response, proc):
        response.write(xml.abortedtasks[(
            xml.taskref(jobid = jobId, taskname = taskName)
            for jobId, taskNames in proc.abortedTasks.items()
            for taskName in taskNames
            )])

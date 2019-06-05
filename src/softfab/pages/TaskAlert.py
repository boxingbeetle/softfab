# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.jobview import alertList
from softfab.pageargs import StrArg
from softfab.pagelinks import JobIdArgs
from softfab.response import Response
from softfab.tasktables import TaskProcessorMixin
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml


class TaskAlert_POST(ControlPage['TaskAlert_POST.Arguments',
                                 'TaskAlert_POST.Processor']):

    class Arguments(JobIdArgs):
        taskId = StrArg()
        runId = StrArg('0')
        alert = StrArg()

    class Processor(TaskProcessorMixin,
                    PageProcessor['TaskAlert_POST.Arguments']):

        def process(self, req, user):
            self.initTask(req)

            runId = req.args.runId
            if runId != '0':
                # We do not support multiple runs of the same task and probably
                # never will, but accept the run ID for backwards compatibility.
                raise InvalidRequest('Invalid run ID "%s"' % runId)

            alert = req.args.alert
            if alert != '' and alert not in alertList:
                raise InvalidRequest('Invalid alert status "%s"' % alert)

            self.task.setAlert(alert)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 't/m', 'set alert status')

    def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.ok)

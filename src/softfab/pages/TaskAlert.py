# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.joblib import jobDB
from softfab.jobview import alertList
from softfab.pageargs import StrArg
from softfab.pagelinks import JobIdArgs
from softfab.userlib import checkPrivilege
from softfab.xmlgen import xml


class TaskAlert_POST(ControlPage['TaskAlert_POST.Arguments', 'TaskAlert_POST.Processor']):

    class Arguments(JobIdArgs):
        taskId = StrArg()
        runId = StrArg('0')
        alert = StrArg()

    class Processor(PageProcessor):

        def process(self, req):
            jobId = req.args.jobId
            taskName = req.args.taskId
            runId = req.args.runId
            if runId != '0':
                # We do not support multiple runs of the same task and probably
                # never will, but accept the run ID for backwards compatibility.
                raise InvalidRequest('Invalid run ID "%s"' % runId)
            alert = req.args.alert
            if alert != '' and alert not in alertList:
                raise InvalidRequest('Invalid alert status "%s"' % alert)
            try:
                job = jobDB[jobId]
            except KeyError:
                raise InvalidRequest('Job "%s" does not exist' % jobId)
            run = job.getTask(taskName)
            if run is None:
                raise InvalidRequest(
                    'Job "%s" does not contain task "%s"'
                    % ( jobId, taskName )
                    )
            run.setAlert(alert)

    def checkAccess(self, req):
        checkPrivilege(req.user, 't/m', 'set alert status')

    def writeReply(self, response, proc):
        response.write(xml.ok)

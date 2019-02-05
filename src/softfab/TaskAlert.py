# SPDX-License-Identifier: BSD-3-Clause

from ControlPage import ControlPage
from Page import InvalidRequest, PageProcessor
from joblib import jobDB
from jobview import alertList
from pageargs import StrArg
from pagelinks import JobIdArgs
from xmlgen import xml

class TaskAlert_POST(ControlPage):

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
        req.checkPrivilege('t/m', 'set alert status')

    def writeReply(self, response, proc):
        response.write(xml.ok)

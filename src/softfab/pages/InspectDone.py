# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.joblib import jobDB
from softfab.pageargs import DictArg, EnumArg, StrArg
from softfab.pagelinks import TaskIdArgs
from softfab.resultcode import ResultCode
from softfab.resultlib import putData
from softfab.xmlgen import xml

class InspectDone_POST(ControlPage['InspectDone_POST.Arguments', 'InspectDone_POST.Processor']):

    class Arguments(TaskIdArgs):
        result = EnumArg(ResultCode)
        summary = StrArg(None)
        data = DictArg(StrArg())

    class Processor(PageProcessor):

        def process(self, req):
            # Fetch and check job and task.
            jobId = req.args.jobId
            try:
                job = jobDB[jobId]
            except KeyError:
                raise InvalidRequest('Job "%s" does not exist' % jobId)
            taskName = req.args.taskName
            task = job.getTask(taskName)
            if task is None:
                raise InvalidRequest(
                    'Job "%s" does not have a task named "%s"'
                    % ( jobId, taskName )
                    )
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
                raise InvalidRequest('Invalid inspection result "%s"' % result)
            summary = req.args.summary

            # Check store permissions.
            req.checkPrivilegeForOwned('t/m', job)

            # Store mid-level data, if any.
            if req.args.data:
                putData(taskName, taskRun.getId(), req.args.data)

            # Store inspection result.
            job.inspectDone(taskName, result, summary)

    def checkAccess(self, req):
        # Error messages might leak info about job/task existence, so make sure
        # at least read-only access is allowed.
        # The processor will do additional checks.
        req.checkPrivilege('j/l')
        req.checkPrivilege('t/l')

    def writeReply(self, response, proc):
        response.write(xml.ok)

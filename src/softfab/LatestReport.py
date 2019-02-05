# SPDX-License-Identifier: BSD-3-Clause

from Page import FabResource, PageProcessor, Redirect
from UIPage import UIPage
from authentication import LoginAuthPage
from joblib import getAllTasksWithId
from pagelinks import TaskDefIdArgs
from resultcode import ResultCode
from xmlgen import xhtml

class LatestReport(UIPage, FabResource):
    authenticationWrapper = LoginAuthPage

    class Arguments(TaskDefIdArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            taskId = req.args.id
            taskTimes = (
                ( task['starttime'], task )
                for task in getAllTasksWithId(taskId)
                if task.getResult() in ( ResultCode.OK, ResultCode.WARNING )
                )
            try:
                starttime_, task = max(taskTimes)
            except ValueError:
                pass # empty sequence; handled by presentContent()
            else:
                raise Redirect(task.getURL())

    def checkAccess(self, req):
        req.checkPrivilege('t/a', 'view task reports')

    def fabTitle(self, proc):
        return 'Latest Report'

    def presentContent(self, proc):
        return xhtml.p[ 'No reports found for task "%s".' % proc.args.id ]

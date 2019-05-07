# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import FabResource, PageProcessor, Redirect
from softfab.UIPage import UIPage
from softfab.authentication import LoginAuthPage
from softfab.joblib import getAllTasksWithId
from softfab.pagelinks import TaskDefIdArgs
from softfab.resultcode import ResultCode
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import XMLContent, xhtml


class LatestReport_GET(
        UIPage['LatestReport_GET.Processor'],
        FabResource['LatestReport_GET.Arguments', 'LatestReport_GET.Processor']
        ):
    authenticator = LoginAuthPage.instance

    class Arguments(TaskDefIdArgs):
        pass

    class Processor(PageProcessor[TaskDefIdArgs]):

        def process(self, req, user):
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

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 't/a', 'view task reports')

    def pageTitle(self, proc: Processor) -> str:
        return 'Latest Report'

    def presentContent(self, proc: Processor) -> XMLContent:
        return xhtml.p[ 'No reports found for task "%s".' % proc.args.id ]

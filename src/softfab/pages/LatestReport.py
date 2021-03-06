# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, cast

from softfab.Page import FabResource, PageProcessor, Redirect
from softfab.UIPage import UIPage
from softfab.authentication import LoginAuthPage
from softfab.joblib import TaskToJobs
from softfab.pagelinks import TaskDefIdArgs, createRunURL
from softfab.request import Request
from softfab.resultcode import ResultCode
from softfab.users import User, checkPrivilege
from softfab.xmlgen import XMLContent, xhtml


class LatestReport_GET(
        UIPage['LatestReport_GET.Processor'],
        FabResource['LatestReport_GET.Arguments', 'LatestReport_GET.Processor']
        ):
    authenticator = LoginAuthPage.instance

    class Arguments(TaskDefIdArgs):
        pass

    class Processor(PageProcessor[TaskDefIdArgs]):

        taskToJobs: ClassVar[TaskToJobs]

        async def process(self,
                          req: Request[TaskDefIdArgs],
                          user: User
                          ) -> None:
            taskId = req.args.id
            taskTimes = (
                ( task.startTime, task )
                for task in self.taskToJobs.iterTasksWithId(taskId)
                if task.result in ( ResultCode.OK, ResultCode.WARNING )
                )
            try:
                starttime_, task = max(taskTimes)
            except ValueError:
                pass # empty sequence; handled by presentContent()
            else:
                run = task.getLatestRun()
                raise Redirect(createRunURL(run, report=None))

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 't/a', 'view task reports')

    def pageTitle(self, proc: Processor) -> str:
        return 'Latest Report'

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(LatestReport_GET.Processor, kwargs['proc'])
        return xhtml.p[ f'No reports found for task "{proc.args.id}".' ]

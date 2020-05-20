# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import ClassVar, cast

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, Redirect
from softfab.formlib import actionButtons, makeForm
from softfab.joblib import JobDB
from softfab.pageargs import EnumArg
from softfab.pagelinks import TaskIdArgs
from softfab.request import Request
from softfab.userlib import User, checkPrivilegeForOwned
from softfab.xmlgen import XMLContent, xhtml

Actions = Enum('Actions', 'ABORT CANCEL')

class AbortTask_GET(FabPage[FabPage.Processor, FabPage.Arguments]):
    icon = 'IconExec'
    iconModifier = IconModifier.DELETE
    description = 'Abort Task'

    class Arguments(TaskIdArgs):
        pass

    def checkAccess(self, user: User) -> None:
        # No permission needed to display the confirmation dialog.
        pass

    def presentContent(self, **kwargs: object) -> XMLContent:
        # Ask for confirmation.
        proc = cast(FabPage.Processor[TaskIdArgs], kwargs['proc'])
        taskName = proc.args.taskName
        if taskName == '/all-waiting':
            yield xhtml.p[ 'Abort all waiting tasks?' ]
        elif taskName == '/all':
            yield xhtml.p[ 'Abort all unfinished tasks?' ]
        else:
            yield xhtml.p[ 'Abort task ', xhtml.b[ taskName ], '?' ]
        yield makeForm(args = proc.args)[
            xhtml.p[ actionButtons(Actions) ]
            ].present(**kwargs)

class AbortTask_POST(FabPage['AbortTask_POST.Processor',
                             'AbortTask_POST.Arguments']):
    icon = 'IconExec'
    iconModifier = IconModifier.DELETE
    description = 'Abort Task'

    class Arguments(TaskIdArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor['AbortTask_POST.Arguments']):

        jobDB: ClassVar[JobDB]

        async def process(self,
                          req: Request['AbortTask_POST.Arguments'],
                          user: User
                          ) -> None:
            # pylint: disable=attribute-defined-outside-init
            jobId = req.args.jobId
            taskName = req.args.taskName
            action = req.args.action

            if action is Actions.CANCEL:
                page = cast(AbortTask_POST, self.page)
                raise Redirect(page.getParentURL(req.args))
            assert action is Actions.ABORT, action

            job = self.jobDB[jobId]
            checkPrivilegeForOwned(
                user, 't/d', job, ('abort tasks in this job', 'abort tasks')
                )
            message: XMLContent
            if taskName == '/all-waiting':
                aborted = job.abortAll(
                    lambda task: task.isWaiting(),
                    user.name
                    )
                if aborted:
                    message = 'All waiting tasks have been aborted.'
                else:
                    message = 'There were no waiting tasks.'
            elif taskName == '/all':
                aborted = job.abortAll(user = user.name)
                if aborted:
                    message = 'All unfinished tasks have been aborted.'
                else:
                    message = 'There were no unfinished tasks.'
            else:
                result = job.abortTask(taskName, user.name)
                message = 'Task ', xhtml.b[ taskName ], ' ', result, '.'
            self.message = message

    def checkAccess(self, user: User) -> None:
        # The permission is checked by the Processor.
        pass

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(AbortTask_POST.Processor, kwargs['proc'])
        yield xhtml.p[ proc.message ]
        yield self.backToParent(proc.args)

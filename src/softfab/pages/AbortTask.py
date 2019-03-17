# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, Redirect
from softfab.formlib import actionButtons, makeForm
from softfab.joblib import jobDB
from softfab.pageargs import EnumArg
from softfab.pagelinks import TaskIdArgs
from softfab.userlib import IUser, checkPrivilegeForOwned
from softfab.xmlgen import XMLContent, xhtml

Actions = Enum('Actions', 'ABORT CANCEL')

class AbortTask_GET(FabPage[FabPage.Processor, FabPage.Arguments]):
    icon = 'IconExec'
    iconModifier = IconModifier.DELETE
    description = 'Abort Task'

    class Arguments(TaskIdArgs):
        pass

    def checkAccess(self, user: IUser) -> None:
        # No permission needed to display the confirmation dialog.
        pass

    def presentContent(self, proc: FabPage.Processor) -> XMLContent:
        # Ask for confirmation.
        taskName = proc.args.taskName
        if taskName == '/all-waiting':
            yield xhtml.p[ 'Abort all waiting tasks?' ]
        elif taskName == '/all':
            yield xhtml.p[ 'Abort all unfinished tasks?' ]
        else:
            yield xhtml.p[ 'Abort task ', xhtml.b[ taskName ], '?' ]
        yield makeForm(args = proc.args)[
            xhtml.p[ actionButtons(Actions) ]
            ].present(proc=proc)

class AbortTask_POST(FabPage['AbortTask_POST.Processor', 'AbortTask_POST.Arguments']):
    icon = 'IconExec'
    iconModifier = IconModifier.DELETE
    description = 'Abort Task'

    class Arguments(TaskIdArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor):

        def process(self, req):
            # pylint: disable=attribute-defined-outside-init
            jobId = req.args.jobId
            taskName = req.args.taskName
            action = req.args.action

            if action is Actions.CANCEL:
                raise Redirect(self.page.getParentURL(req))
            assert action is Actions.ABORT, action

            job = jobDB[jobId]
            checkPrivilegeForOwned(
                req.user, 't/d', job, ('abort tasks in this job', 'abort tasks')
                )
            if taskName == '/all-waiting':
                aborted = job.abortAll(
                    lambda task: task.isWaiting(),
                    req.userName
                    )
                if aborted:
                    message = 'All waiting tasks have been aborted.'
                else:
                    message = 'There were no waiting tasks.'
            elif taskName == '/all':
                aborted = job.abortAll(user = req.userName)
                if aborted:
                    message = 'All unfinished tasks have been aborted.'
                else:
                    message = 'There were no unfinished tasks.'
            else:
                message = taskName, job.abortTask(
                    taskName, req.userName
                    )
            self.message = message

    def checkAccess(self, user: IUser) -> None:
        # The permission is checked by the Processor.
        pass

    def presentContent(self, proc: Processor) -> XMLContent:
        message = proc.message
        if isinstance(message, tuple):
            yield xhtml.p[
                'Task ', xhtml.b[ message[0] ], ' ', message[1], '.'
                ]
        else:
            yield xhtml.p[ message ]
        yield self.backToParent(proc.req)

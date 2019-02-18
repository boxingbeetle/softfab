# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, Redirect
from softfab.formlib import actionButtons, makeForm
from softfab.joblib import jobDB
from softfab.pageargs import EnumArg
from softfab.pagelinks import TaskIdArgs
from softfab.xmlgen import xhtml

from enum import Enum

Actions = Enum('Actions', 'ABORT CANCEL')

class AbortTask_GET(FabPage):
    icon = 'IconExec'
    iconModifier = IconModifier.DELETE
    description = 'Abort Task'

    class Arguments(TaskIdArgs):
        pass

    def checkAccess(self, req):
        # No permission needed to display the confirmation dialog.
        pass

    def presentContent(self, proc):
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

class AbortTask_POST(FabPage):
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
            # The next line is safe with respect to 'None' values,
            # because 'getUserName()' can return None only when security
            # is disabled.
            req.checkPrivilegeForOwned(
                't/d', job, ('abort tasks in this job', 'abort tasks')
                )
            if taskName == '/all-waiting':
                aborted = job.abortAll(
                    lambda task: task.isWaiting(),
                    req.getUserName()
                    )
                if aborted:
                    message = 'All waiting tasks have been aborted.'
                else:
                    message = 'There were no waiting tasks.'
            elif taskName == '/all':
                aborted = job.abortAll(user = req.getUserName())
                if aborted:
                    message = 'All unfinished tasks have been aborted.'
                else:
                    message = 'There were no unfinished tasks.'
            else:
                message = taskName, job.abortTask(
                    taskName, req.getUserName()
                    )
            self.message = message

    def checkAccess(self, req):
        # The permission is checked by the Processor.
        pass

    def presentContent(self, proc):
        message = proc.message
        if isinstance(message, tuple):
            yield xhtml.p[
                'Task ', xhtml.b[ message[0] ], ' ', message[1], '.'
                ]
        else:
            yield xhtml.p[ message ]
        yield self.backToParent(proc.req)
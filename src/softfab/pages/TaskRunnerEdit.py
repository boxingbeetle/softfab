# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import InvalidRequest, PageProcessor, Redirect
from softfab.formlib import actionButtons, makeForm
from softfab.pageargs import EnumArg, PageArgs, StrArg
from softfab.taskrunnerlib import taskRunnerDB
from softfab.resourceview import CapabilitiesPanel, CommentPanel
from softfab.xmlgen import xhtml

from enum import Enum

Actions = Enum('Actions', 'SAVE CANCEL')

class PostArgs(PageArgs):
    id = StrArg()
    capabilities = StrArg()
    description = StrArg()

class TaskRunnerEdit_GET(FabPage):
    icon = 'IconResources'
    description = 'Edit Task Runner'
    linkDescription = False

    class Arguments(PageArgs):
        id = StrArg()

    class Processor(PageProcessor):

        def process(self, req):
            try:
                runner = taskRunnerDB[req.args.id]
            except KeyError:
                raise InvalidRequest(
                    'Task Runner "%s" does not exist' % req.args.id
                    )

            # pylint: disable=attribute-defined-outside-init
            self.runner = runner

    def checkAccess(self, req):
        req.checkPrivilege('tr/m')

    def presentContent(self, proc):
        args = proc.args
        runner = proc.runner
        yield xhtml.h2[ 'Task Runner: ', xhtml.b[ args.id ]]
        yield makeForm(
            args=PostArgs(
                args,
                capabilities=' '.join(sorted(runner.capabilities)),
                description=runner.description
                )
            )[
            CapabilitiesPanel.instance,
            CommentPanel.instance,
            xhtml.p[ actionButtons(Actions) ]
            ].present(proc=proc)

    def presentError(self, proc, message):
        yield message
        yield self.backToParent(proc.req)

class TaskRunnerEdit_POST(TaskRunnerEdit_GET):

    class Arguments(PostArgs):
        action = EnumArg(Actions)

    class Processor(TaskRunnerEdit_GET.Processor):

        def process(self, req):
            if req.args.action is Actions.SAVE:
                super().process(req)
                args = req.args
                runner = self.runner
                runner.capabilities = args.capabilities.split()
                runner.description = args.description

            raise Redirect(self.page.getParentURL(req))

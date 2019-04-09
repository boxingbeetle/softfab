# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum

from softfab.FabPage import FabPage
from softfab.Page import InvalidRequest, PageProcessor, Redirect
from softfab.formlib import actionButtons, makeForm
from softfab.pageargs import EnumArg, PageArgs, StrArg
from softfab.resourcelib import taskRunnerDB
from softfab.resourceview import CapabilitiesPanel, CommentPanel
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import XML, XMLContent, xhtml

Actions = Enum('Actions', 'SAVE CANCEL')

class PostArgs(PageArgs):
    id = StrArg()
    capabilities = StrArg()
    description = StrArg()

class TaskRunnerEdit_GET(FabPage['TaskRunnerEdit_GET.Processor',
                                 'TaskRunnerEdit_GET.Arguments']):
    icon = 'IconResources'
    description = 'Edit Task Runner'
    linkDescription = False

    class Arguments(PageArgs):
        id = StrArg()

    class Processor(PageProcessor['TaskRunnerEdit_GET.Arguments']):

        def process(self, req, user):
            try:
                runner = taskRunnerDB[req.args.id]
            except KeyError:
                raise InvalidRequest(
                    'Task Runner "%s" does not exist' % req.args.id
                    )

            # pylint: disable=attribute-defined-outside-init
            self.runner = runner

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'tr/m')

    def presentContent(self, proc: Processor) -> XMLContent:
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

    def presentError(self, proc: Processor, message: XML) -> XMLContent:
        yield message
        yield self.backToParent(proc.req)

class TaskRunnerEdit_POST(TaskRunnerEdit_GET):

    class Arguments(PostArgs):
        action = EnumArg(Actions)

    class Processor(TaskRunnerEdit_GET.Processor):

        def process(self, req, user):
            if req.args.action is Actions.SAVE:
                super().process(req, user)
                args = req.args
                runner = self.runner
                runner.capabilities = args.capabilities.split()
                runner.description = args.description

            raise Redirect(self.page.getParentURL(req))

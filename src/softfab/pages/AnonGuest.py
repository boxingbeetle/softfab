# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import ArgT, PageProcessor, ProcT, Redirect
from softfab.pagelinks import AnonGuestArgs
from softfab.projectlib import project
from softfab.userlib import checkPrivilege
from softfab.userview import presentAnonGuestSetting
from softfab.xmlgen import XMLContent


class AnonGuestBase(FabPage[ProcT, ArgT]):
    icon = 'UserList1'
    description = 'Anonymous Guests'
    linkDescription = False

    def pageTitle(self, proc: ProcT) -> str:
        return 'Anonymous Guest Access'

    def presentContent(self, proc: ProcT) -> XMLContent:
        raise NotImplementedError

class AnonGuest_GET(AnonGuestBase[FabPage.Processor, FabPage.Arguments]):

    def checkAccess(self, req):
        pass

    def presentContent(self, proc: FabPage.Processor) -> XMLContent:
        yield presentAnonGuestSetting()
        yield self.backToParent(proc.req)

class AnonGuest_POST(AnonGuestBase['AnonGuest_POST.Processor',
                                   'AnonGuest_POST.Arguments']):

    def checkAccess(self, req):
        checkPrivilege(req.user, 'p/m', 'change project settings')

    class Arguments(AnonGuestArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            project.setAnonGuestAccess(req.args.anonguest)
            raise Redirect('AnonGuest')

    def presentContent(self, proc: Processor) -> XMLContent:
        assert False

    def presentError(self, proc: Processor, message: str) -> XMLContent:
        yield message
        yield self.backToParent(proc.req)

# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, ProcT, Redirect
from softfab.pagelinks import AnonGuestArgs
from softfab.projectlib import project
from softfab.userview import presentAnonGuestSetting
from softfab.xmlgen import XMLContent

class AnonGuestBase(FabPage[ProcT]):
    icon = 'UserList1'
    description = 'Anonymous Guests'
    linkDescription = False

    def pageTitle(self, proc: ProcT) -> str:
        return 'Anonymous Guest Access'

    def presentContent(self, proc):
        raise NotImplementedError

class AnonGuest_GET(AnonGuestBase[FabPage.Processor]):

    def checkAccess(self, req):
        pass

    def presentContent(self, proc):
        yield presentAnonGuestSetting()
        yield self.backToParent(proc.req)

class AnonGuest_POST(AnonGuestBase['AnonGuest_POST.Processor']):

    def checkAccess(self, req):
        req.checkPrivilege('p/m', 'change project settings')

    class Arguments(AnonGuestArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            project.setAnonGuestAccess(req.args.anonguest)
            raise Redirect('AnonGuest')

    def presentContent(self, proc):
        assert False

    def presentError(self, proc: Processor, message: str) -> XMLContent:
        yield message
        yield self.backToParent(proc.req)

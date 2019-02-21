# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, Redirect
from softfab.pagelinks import AnonGuestArgs
from softfab.projectlib import project
from softfab.userview import presentAnonGuestSetting

class AnonGuest_GET(FabPage):
    icon = 'UserList1'
    description = 'Anonymous Guests'
    linkDescription = False

    def fabTitle(self, proc):
        return 'Anonymous Guest Access'

    def checkAccess(self, req):
        pass

    def presentContent(self, proc):
        yield presentAnonGuestSetting()
        yield self.backToParent(proc.req)

class AnonGuest_POST(AnonGuest_GET):

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

    def presentError(self, proc, message):
        yield message
        yield self.backToParent(proc.req)

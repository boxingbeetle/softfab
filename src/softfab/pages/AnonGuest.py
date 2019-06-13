# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, ProcT, Redirect
from softfab.pageargs import ArgsT
from softfab.pagelinks import AnonGuestArgs
from softfab.projectlib import project
from softfab.userlib import User, checkPrivilege
from softfab.userview import presentAnonGuestSetting
from softfab.xmlgen import XML, XMLContent


class AnonGuestBase(FabPage[ProcT, ArgsT]):
    icon = 'IconUser'
    iconModifier = IconModifier.EDIT
    description = 'Anonymous Guests'
    linkDescription = False

    def pageTitle(self, proc: ProcT) -> str:
        return 'Anonymous Guest Access'

    def presentContent(self, proc: ProcT) -> XMLContent:
        raise NotImplementedError

class AnonGuest_GET(AnonGuestBase[FabPage.Processor, FabPage.Arguments]):

    def checkAccess(self, user: User) -> None:
        pass

    def presentContent(self, proc: FabPage.Processor) -> XMLContent:
        yield presentAnonGuestSetting()
        yield self.backToParent(proc.args)

class AnonGuest_POST(AnonGuestBase['AnonGuest_POST.Processor',
                                   'AnonGuest_POST.Arguments']):

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'p/m', 'change project settings')

    class Arguments(AnonGuestArgs):
        pass

    class Processor(PageProcessor[Arguments]):

        def process(self, req, user):
            project.setAnonGuestAccess(req.args.anonguest)
            raise Redirect('AnonGuest')

    def presentContent(self, proc: Processor) -> XMLContent:
        assert False

    def presentError(self, proc: Processor, message: XML) -> XMLContent:
        yield message
        yield self.backToParent(proc.args)

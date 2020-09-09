# SPDX-License-Identifier: BSD-3-Clause

from typing import cast

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, ProcT, Redirect
from softfab.pageargs import ArgsT
from softfab.pagelinks import AnonGuestArgs
from softfab.request import Request
from softfab.users import User, checkPrivilege
from softfab.userview import presentAnonGuestSetting
from softfab.xmlgen import XML, XMLContent


class AnonGuestBase(FabPage[ProcT, ArgsT]):
    icon = 'IconUser'
    iconModifier = IconModifier.EDIT
    description = 'Anonymous Guests'
    linkDescription = False

    def pageTitle(self, proc: ProcT) -> str:
        return 'Anonymous Guest Access'

    def presentContent(self, **kwargs: object) -> XMLContent:
        raise NotImplementedError

class AnonGuest_GET(AnonGuestBase[FabPage.Processor, FabPage.Arguments]):

    def checkAccess(self, user: User) -> None:
        pass

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(FabPage.Processor, kwargs['proc'])
        yield presentAnonGuestSetting(proc.project)
        yield self.backToParent(proc.args)

class AnonGuest_POST(AnonGuestBase['AnonGuest_POST.Processor',
                                   'AnonGuest_POST.Arguments']):

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'p/m', 'change project settings')

    class Arguments(AnonGuestArgs):
        pass

    class Processor(PageProcessor[Arguments]):

        async def process(self,
                          req: Request['AnonGuest_POST.Arguments'],
                          user: User
                          ) -> None:
            self.project.setAnonGuestAccess(req.args.anonguest)
            raise Redirect('AnonGuest')

    def presentContent(self, **kwargs: object) -> XMLContent:
        assert False

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        proc = cast(AnonGuest_POST.Processor, kwargs['proc'])
        yield message
        yield self.backToParent(proc.args)

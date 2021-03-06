# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum, auto
from typing import ClassVar, Iterator, Tuple, cast

from twisted.cred.error import LoginFailed

from softfab.Page import (
    FabResource, PageProcessor, PresentableError, ProcT, Redirect
)
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.formlib import (
    FormTable, actionButtons, makeForm, passwordInput, textInput
)
from softfab.pageargs import ArgsCorrected, ArgsT, EnumArg
from softfab.pagelinks import URLArgs
from softfab.request import Request
from softfab.userlib import User, UserDB, authenticateUser
from softfab.users import Credentials
from softfab.userview import (
    LoginNameArgs, LoginPassArgs, PasswordMessage, PasswordMsgArgs,
    passwordQuality
)
from softfab.webgui import pageURL
from softfab.xmlgen import XML, XMLContent, xhtml


class LoginTable(FormTable):

    def iterFields(self, **kwargs: object) -> Iterator[Tuple[str, XMLContent]]:
        proc = cast(PageProcessor[LoginNameArgs], kwargs['proc'])
        yield 'User name', textInput(name='loginname',
                                     autofocus=not proc.args.loginname)
        yield 'Password', passwordInput(name='loginpass')

class Actions(Enum):
    LOG_IN = auto()
    CANCEL = auto()

class LoginBase(UIPage[ProcT], FabResource[ArgsT, ProcT]):
    authenticator = NoAuthPage.instance

    def checkAccess(self, user: User) -> None:
        pass

    def pageTitle(self, proc: ProcT) -> str:
        return 'Log In'

    def iterActions(self, proc: ProcT) -> Iterator[Actions]:
        yield Actions.LOG_IN
        if proc.project.anonguest:
            yield Actions.CANCEL

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ProcT, kwargs['proc'])
        yield makeForm(args = proc.args)[
            LoginTable.instance,
            xhtml.p[ actionButtons(*self.iterActions(proc)) ]
            ].present(**kwargs)

        userAgent = proc.req.userAgent
        if userAgent.family == 'MSIE':
            yield xhtml.p[
                'Internet Explorer is ', xhtml.b['not supported'],
                ' by SoftFab. Please upgrade to ',
                xhtml.a(href=_downloadURLs['Edge'], target='_blank')[
                    'Microsoft Edge'
                    ], ' or to an alternative browser such as ',
                xhtml.a(href=_downloadURLs['Mozilla'], target='_blank')[
                    'Mozilla Firefox'
                    ], ' or ',
                xhtml.a(href=_downloadURLs['Chrome'], target='_blank')[
                    'Google Chrome'
                    ], '.'
                ]

class Login_GET(LoginBase['Login_GET.Processor', 'Login_GET.Arguments']):
    '''Page that presents login form.
    '''

    class Arguments(LoginNameArgs, URLArgs):
        pass

    class Processor(PageProcessor['Login_GET.Arguments']):

        userDB: ClassVar[UserDB]

        async def process(self,
                          req: Request['Login_GET.Arguments'],
                          user: User
                          ) -> None:
            url = req.args.url
            if url is not None:
                # Only accept relative URLs.
                url = req.relativeURL(url)
                if url is None:
                    raise ArgsCorrected(req.args, url=None)

            # If there are no user accounts, provide setup instructions
            # instead of a login prompt.
            # pylint: disable=attribute-defined-outside-init
            self.setup = not self.userDB

    def pageTitle(self, proc: 'Login_GET.Processor') -> str:
        return 'Setup' if proc.setup else super().pageTitle(proc)

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(Login_GET.Processor, kwargs['proc'])
        if proc.setup:
            return self.__presentSetup()
        else:
            return super().presentContent(**kwargs)

    def __presentSetup(self) -> XMLContent:
        yield xhtml.h3[
            "This factory has no user accounts."
            ]
        yield xhtml.p[
            "To add an operator account (user with administrative privileges), "
            "run the following command on the server that hosts "
            "the SoftFab Control Center:"
            ]
        yield xhtml.p[xhtml.code[
            "$ softfab --dir ", xhtml.em['datadir'], " user add "
            "--role operator ", xhtml.em['name']
            ]]
        yield xhtml.p[
            "where ", xhtml.code[xhtml.em['datadir']], " is the directory "
            "that contains ", xhtml.code['softfab.ini'],
            " and ", xhtml.code[xhtml.em['name']], " is the login name you "
            "pick for the operator account."
            ]
        yield xhtml.p[
            "The command above will print a URL that you can open in your "
            "web browser to set a password for the new operator account. "
            "You can then log in to that account and complete the setup."
            ]

_downloadURLs = {
    'Edge':
        'https://www.microsoft.com/edge',
    'Mozilla':
        'https://www.mozilla.com/firefox/',
    'Chrome':
        'https://www.google.com/chrome/',
    }

class Login_POST(LoginBase['Login_POST.Processor', 'Login_POST.Arguments']):
    '''Page that handles submitted login form.
    '''

    class Arguments(Login_GET.Arguments, LoginPassArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor['Login_POST.Arguments']):

        userDB: ClassVar[UserDB]

        async def process(self,
                          req: Request['Login_POST.Arguments'],
                          user: User
                          ) -> None:
            if req.args.action is not Actions.LOG_IN:
                raise Redirect(req.args.url or 'Home')

            credentials = Credentials(req.args.loginname, req.args.loginpass)
            try:
                user = await authenticateUser(self.userDB, credentials)
            except LoginFailed:
                raise PresentableError(
                    xhtml.p(class_='notice')['Login failed']
                    )
            else:
                # Inactive users are not allowed to log in.
                if not user.isActive():
                    raise PresentableError(
                        xhtml.p(class_='notice')['User account inactive']
                        )
                # Remember logged in user.
                # Starting a new session after login blocks session fixation
                # attacks that inject a valid session cookie that was
                # generated for a different client.
                #   http://en.wikipedia.org/wiki/Session_fixation
                req.startSession(user)

                if passwordQuality(credentials) is not PasswordMessage.SUCCESS \
                        and user.hasPrivilege('u/mo'):
                    # Suggest the user to pick a stronger password.
                    raise Redirect(pageURL(
                        'ChangePassword',
                        PasswordMsgArgs(msg=PasswordMessage.POOR)
                        ))
                else:
                    raise Redirect(req.args.url or 'Home')

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield message
        yield self.presentContent(**kwargs)

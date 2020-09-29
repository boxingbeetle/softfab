# SPDX-License-Identifier: BSD-3-Clause

from typing import Any, ClassVar, Iterator, Optional, Tuple, cast

from twisted.cred.error import UnauthorizedLogin

from softfab.Page import FabResource, PageProcessor, PresentableError, ProcT
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.config import rootURL
from softfab.formlib import FormTable, makeForm, passwordInput, submitButton
from softfab.pageargs import ArgsT, PasswordArg
from softfab.pagelinks import PasswordSetArgs
from softfab.request import Request
from softfab.tokens import Token, TokenDB, TokenRole, authenticateToken
from softfab.userlib import UserDB, setPassword
from softfab.users import Credentials, User
from softfab.userview import (
    LoginNameArgs, PasswordMessage, passwordQuality, passwordStr
)
from softfab.webgui import pageURL
from softfab.xmlgen import XML, XMLContent, xhtml


def presentForm(**kwargs: object) -> XMLContent:
    proc = cast(PageProcessor[PasswordSetArgs], kwargs['proc'])
    return makeForm(args=proc.args)[
        presentFormBody(**kwargs)
        ].present(**kwargs)

def presentFormBody(**kwargs: object) -> XMLContent:
    proc = cast(SetPassword_GET.Processor, kwargs['proc'])
    yield xhtml.p[
        'Please enter a new password for user ', xhtml.b[ proc.userName ], ':'
        ]
    yield NewPasswordTable.instance
    yield xhtml.p[ submitButton ]

class NewPasswordTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, **kwargs: object) -> Iterator[Tuple[str, XMLContent]]:
        yield 'New password', passwordInput(name = 'password')
        yield 'New password (again)', passwordInput(name = 'password2')

def verifyToken(tokenDB: TokenDB, args: PasswordSetArgs) -> Token:
    """Verify a password reset token.

    @return: A valid token matching the given arguments.
    @raise PresentableError: If there is no valid token corresponding to
        the given arguments.
    """
    tokenId = args.token
    credentials = Credentials(tokenId, args.secret)
    try:
        token = authenticateToken(tokenDB, credentials)
    except KeyError as ex:
        raise PresentableError(xhtml[
            f'Token {tokenId} does not exist. '
            f'Perhaps it was already used?'
            ]) from ex
    except UnauthorizedLogin as ex:
        raise PresentableError(xhtml[
            f'The provided secret was not correct for token {tokenId}: {ex}'
            ]) from ex
    if token.role is not TokenRole.PASSWORD_RESET:
        raise PresentableError(xhtml[
            f'Token {tokenId} is not a password reset token.'
            ])
    if token.expired:
        raise PresentableError(xhtml[
            f'Token {tokenId} has expired. '
            f'Please ask the factory operator to reset the password.'
            ])
    return token

class SetPasswordBase(UIPage[ProcT], FabResource[ArgsT, ProcT]):
    authenticator = NoAuthPage.instance

    def loginURL(self, **kwargs: Any) -> str:
        userName = cast(Optional[str], kwargs['proc'].userName)
        return pageURL('Login', LoginNameArgs(loginname=userName))

    def checkAccess(self, user: User) -> None:
        pass

    def pageTitle(self, proc: ProcT) -> str:
        return 'Set Password'

    def iterStyleDefs(self) -> Iterator[str]:
        yield 'td.formlabel { width: 16em; }'

    def presentContent(self, **kwargs: object) -> XMLContent:
        raise NotImplementedError

class SetPassword_GET(SetPasswordBase['SetPassword_GET.Processor',
                                      'SetPassword_GET.Arguments']):

    class Arguments(PasswordSetArgs):
        pass

    class Processor(PageProcessor['SetPassword_GET.Arguments']):

        userDB: ClassVar[UserDB]
        tokenDB: ClassVar[TokenDB]

        async def process(self,
                          req: Request['SetPassword_GET.Arguments'],
                          user: User
                          ) -> None:
            # pylint: disable=attribute-defined-outside-init

            try:
                token = verifyToken(self.tokenDB, req.args)
            except PresentableError:
                self.userName = None
                raise
            else:
                self.userName = token.getParam('name')

    def presentContent(self, **kwargs: object) -> XMLContent:
        # Remove the token credentials from the history and location bar.
        url = f"{rootURL}SetPassword"
        yield xhtml.script[
            f"history.replaceState(null, '', '{url}');"
            ]

        yield presentForm(**kwargs)

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield xhtml.p(class_='notice')[ message ]

class SetPassword_POST(SetPasswordBase['SetPassword_POST.Processor',
                                       'SetPassword_POST.Arguments']):

    class Arguments(PasswordSetArgs):
        password = PasswordArg()
        password2 = PasswordArg()

    class Processor(PageProcessor['SetPassword_POST.Arguments']):

        userDB: ClassVar[UserDB]
        tokenDB: ClassVar[TokenDB]

        async def process(self,
                          req: Request['SetPassword_POST.Arguments'],
                          user: User
                          ) -> None:
            # pylint: disable=attribute-defined-outside-init

            try:
                token = verifyToken(self.tokenDB, req.args)
            except PresentableError:
                self.userName = None
                raise
            else:
                self.userName = userName = token.getParam('name')

            password = req.args.password
            credentials = Credentials(userName, password)
            if password == req.args.password2:
                quality = passwordQuality(credentials)
            else:
                quality = PasswordMessage.MISMATCH
            if quality is not PasswordMessage.SUCCESS:
                raise PresentableError(xhtml[passwordStr[quality]])

            try:
                setPassword(self.userDB, credentials)
            except ValueError as ex:
                raise PresentableError(xhtml[ex.args[0]])
            else:
                self.tokenDB.remove(token)

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        proc = cast(SetPassword_POST.Processor, kwargs['proc'])
        yield xhtml.p(class_='notice')[ message ]
        if proc.userName is not None:
            yield presentForm(**kwargs)

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield xhtml.p[
            'Password set successfully.'
            ]
        yield xhtml.p[
            'You can now ', xhtml.a(href=self.loginURL(**kwargs))['log in'],
            ' with your new password.'
            ]

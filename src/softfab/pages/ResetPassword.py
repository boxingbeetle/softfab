# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import ClassVar, Iterator, Tuple, cast

from twisted.cred.error import LoginFailed

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.formlib import (
    FormTable, actionButtons, hiddenInput, makeForm, passwordInput
)
from softfab.pageargs import EnumArg, PasswordArg, RefererArg
from softfab.pagelinks import UserIdArgs
from softfab.request import Request
from softfab.userlib import (
    User, UserDB, authenticateUser, checkPrivilege, setPassword
)
from softfab.userview import (
    LoginPassArgs, PasswordMessage, PasswordMsgArgs, passwordQuality,
    passwordStr
)
from softfab.webgui import pageURL
from softfab.xmlgen import XML, XMLContent, xhtml


def presentForm(**kwargs: object) -> XMLContent:
    proc = cast(PageProcessor[UserIdArgs], kwargs['proc'])
    return makeForm(args = proc.args)[
        presentFormBody(**kwargs)
        ].present(**kwargs)

def presentFormBody(**kwargs: object) -> XMLContent:
    proc = cast(PageProcessor[UserIdArgs], kwargs['proc'])
    yield xhtml.p[
        'Please enter a new password for user ', xhtml.b[ proc.args.user ], ':'
        ]
    yield NewPasswordTable.instance
    if proc.user.name is None:
        yield hiddenInput(name='loginpass', value='')
    else:
        yield xhtml.p[
            'To verify your identity, '
            'please also enter your own password:'
            ]
        yield ReqPasswordTable.instance
    yield xhtml.p[ actionButtons(Actions) ]

class NewPasswordTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, **kwargs: object) -> Iterator[Tuple[str, XMLContent]]:
        yield 'New password', passwordInput(name = 'password')
        yield 'New password (again)', passwordInput(name = 'password2')

class ReqPasswordTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, **kwargs: object) -> Iterator[Tuple[str, XMLContent]]:
        yield 'Operator password', passwordInput(name='loginpass')

Actions = Enum('Actions', 'CHANGE CANCEL')

class ResetPassword_GET(FabPage['ResetPassword_GET.Processor',
                                'ResetPassword_GET.Arguments']):
    icon = 'IconUser'
    iconModifier = IconModifier.EDIT
    description = 'Reset Password'

    class Arguments(UserIdArgs, PasswordMsgArgs):
        indexQuery = RefererArg('UserList')
        detailsQuery = RefererArg('UserDetails')

    class Processor(PageProcessor['ResetPassword_GET.Arguments']):

        userDB: ClassVar[UserDB]

        async def process(self,
                          req: Request['ResetPassword_GET.Arguments'],
                          user: User
                          ) -> None:
            # pylint: disable=attribute-defined-outside-init

            # Check if user name exists in the DB.
            userName = req.args.user
            if userName not in self.userDB:
                self.retry = False
                raise PresentableError(xhtml[
                    f'User "{userName}" does not exist (anymore)'
                    ])

            # Check if msg has been set and act upon accordingly.
            msg = req.args.msg
            if msg is not None:
                self.retry = msg is not PasswordMessage.SUCCESS
                raise PresentableError(xhtml[passwordStr[msg]])

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'u/m', "reset passwords")

    def iterStyleDefs(self) -> Iterator[str]:
        yield 'td.formlabel { width: 16em; }'

    def presentContent(self, **kwargs: object) -> XMLContent:
        return presentForm(**kwargs)

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        proc = cast(ResetPassword_GET.Processor, kwargs['proc'])
        yield xhtml.p(class_ = 'notice')[ message ]
        if proc.retry:
            yield presentForm(**kwargs)
        else:
            yield self.backToReferer(proc.args)


class ResetPassword_POST(FabPage['ResetPassword_POST.Processor',
                                 'ResetPassword_POST.Arguments']):
    # Icon is determined by the GET variant of the page.
    # TODO: This asymmetry isn't good.
    #       Either give treat both the GET and POST handlers as full pages
    #       with their own icon etc (see FabPage.__pageInfo), or move the
    #       icon etc. to a per-module container.
    icon = None
    description = 'Reset Password'

    class Arguments(ResetPassword_GET.Arguments, LoginPassArgs):
        action = EnumArg(Actions)
        password = PasswordArg()
        password2 = PasswordArg()

    class Processor(PageProcessor['ResetPassword_POST.Arguments']):

        userDB: ClassVar[UserDB]

        async def process(self,
                          req: Request['ResetPassword_POST.Arguments'],
                          user: User
                          ) -> None:
            # pylint: disable=attribute-defined-outside-init

            if req.args.action is Actions.CANCEL:
                page = cast(ResetPassword_POST, self.page)
                raise Redirect(page.getCancelURL(req.args))
            elif req.args.action is Actions.CHANGE:
                userDB = self.userDB

                # Validate input.
                userName = req.args.user
                if userName not in userDB:
                    self.retry = False
                    raise PresentableError(xhtml[
                        f'User "{userName}" does not exist (anymore)'
                        ])

                password = req.args.password
                if password == req.args.password2:
                    quality = passwordQuality(userName, password)
                else:
                    quality = PasswordMessage.MISMATCH
                if quality is not PasswordMessage.SUCCESS:
                    self.retry = True
                    raise PresentableError(xhtml[passwordStr[quality]])

                reqUserName = user.name # get current logged-in user
                if reqUserName is not None:
                    try:
                        user_ = await authenticateUser(
                            userDB, reqUserName, req.args.loginpass
                            )
                    except LoginFailed as ex:
                        self.retry = True
                        raise PresentableError(xhtml[
                            "Verification of operator password failed",
                            f": {ex.args[0]}" if ex.args else None,
                            "."
                            ])

                # Apply changes.
                try:
                    setPassword(userDB, userName, password)
                except ValueError as ex:
                    self.retry = True
                    raise PresentableError(xhtml[ex.args[0]])
                else:
                    # Successfully changed password
                    raise Redirect(pageURL(
                        'ResetPassword',
                        PasswordMsgArgs(
                            user = userName, msg = PasswordMessage.SUCCESS
                            )
                        ))
            else:
                assert False, req.args.action

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'u/m', "reset passwords")

    def getCancelURL(self, args: Arguments) -> str:
        return args.refererURL or self.getParentURL(args)

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        proc = cast(ResetPassword_POST.Processor, kwargs['proc'])
        yield xhtml.p(class_ = 'notice')[ message ]
        if proc.retry:
            yield presentForm(**kwargs)
        else:
            yield self.backToReferer(proc.args)

    def presentContent(self, **kwargs: object) -> XMLContent:
        assert False

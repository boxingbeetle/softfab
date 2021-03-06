# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import ClassVar, Iterator, Optional, Tuple, cast

from twisted.cred.error import LoginFailed

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, PresentableError, ProcT, Redirect
from softfab.formlib import (
    FormTable, actionButtons, dropDownList, hiddenInput, makeForm,
    passwordInput, textInput
)
from softfab.pageargs import ArgsT, EnumArg, PageArgs, RefererArg, StrArg
from softfab.request import Request
from softfab.roles import UIRoleNames, uiRoleToSet
from softfab.tokens import TokenDB
from softfab.userlib import (
    UserDB, addUserAccount, authenticateUser, resetPassword
)
from softfab.users import Credentials, User, checkPrivilege
from softfab.userview import LoginPassArgs, presentSetPasswordURL
from softfab.xmlgen import XML, XMLContent, xhtml

Actions = Enum('Actions', 'ADD CANCEL')

class AddUserBase(FabPage[ProcT, ArgsT]):
    icon = 'IconUser'
    iconModifier = IconModifier.NEW
    description = 'Add User'

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'u/c', 'add new users')

    def iterStyleDefs(self) -> Iterator[str]:
        yield 'td.formlabel { width: 16em; }'

    def presentContent(self, **kwargs: object) -> XMLContent:
        raise NotImplementedError

    def presentForm(self,
            prefill: Optional[PageArgs], **kwargs: object
            ) -> XMLContent:
        proc = cast(ProcT, kwargs['proc'])
        return makeForm(args = prefill)[
            self.__presentFormBody(proc.user)
            ].present(**kwargs)

    def __presentFormBody(self, user: User) -> XMLContent:
        yield xhtml.p[ 'Enter information about new user:' ]
        yield UserTable.instance
        if user.name is None:
            yield hiddenInput(name='loginpass', value='')
        else:
            yield xhtml.p[
                'To verify your identity, '
                'please also enter your own password:'
                ]
            yield ReqPasswordTable.instance
        yield xhtml.p[ actionButtons(Actions) ]

    def getCancelURL(self, args: ArgsT) -> str:
        return args.refererURL or self.getParentURL(args)

class AddUser_GET(AddUserBase['AddUser_GET.Processor',
                              'AddUser_GET.Arguments']):

    class Arguments(PageArgs):
        indexQuery = RefererArg('UserList')

    class Processor(PageProcessor['AddUser_GET.Arguments']):
        async def process(self,
                          req: Request['AddUser_GET.Arguments'],
                          user: User
                          ) -> None:
            pass

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield self.presentForm(RoleArgs(role=UIRoleNames.USER), **kwargs)

class RoleArgs(PageArgs):
    role = EnumArg(UIRoleNames)

class AddUser_POST(AddUserBase['AddUser_POST.Processor',
                               'AddUser_POST.Arguments']):

    class Arguments(AddUser_GET.Arguments, LoginPassArgs, RoleArgs):
        action = EnumArg(Actions)
        user = StrArg()

    class Processor(PageProcessor['AddUser_POST.Arguments']):

        userDB: ClassVar[UserDB]
        tokenDB: ClassVar[TokenDB]

        async def process(self,
                          req: Request['AddUser_POST.Arguments'],
                          user: User
                          ) -> None:
            if req.args.action is Actions.CANCEL:
                page = cast(AddUser_POST, self.page)
                raise Redirect(page.getCancelURL(req.args))
            elif req.args.action is Actions.ADD:
                userDB = self.userDB

                # Validate input.
                userName = req.args.user
                if not userName:
                    raise PresentableError(xhtml['User name cannot be empty.'])

                # Authenticate currently logged-in operator.
                reqUserName = user.name
                if reqUserName is not None:
                    operatorCred = Credentials(reqUserName, req.args.loginpass)
                    try:
                        user_ = await authenticateUser(userDB, operatorCred)
                    except LoginFailed as ex:
                        raise PresentableError(xhtml[
                            'Operator authentication failed%s.' % (
                                ': ' + str(ex) if str(ex) else ''
                                )
                            ])

                # Create new user account.
                try:
                    roles = uiRoleToSet(req.args.role)
                    addUserAccount(userDB, userName, roles)
                except ValueError as ex:
                    raise PresentableError(xhtml[f'{ex}.'])

                # Create a password reset token for the new account.
                # pylint: disable=attribute-defined-outside-init
                self.token = resetPassword(userDB, userName, self.tokenDB)
            else:
                assert False, req.args.action

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(AddUser_POST.Processor, kwargs['proc'])
        yield xhtml.p[ xhtml.b[
            f'User "{proc.args.user}" has been added successfully.'
            ] ]
        yield presentSetPasswordURL(proc.args.user, proc.token)
        yield xhtml.hr
        yield xhtml.p[
            'You can use the form below to add another user, or ',
            xhtml.a(href = self.getCancelURL(proc.args))[
                'go back to the users overview page'
                ], '.'
            ]
        yield self.presentForm(RoleArgs(role=UIRoleNames.USER), **kwargs)

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        proc = cast(AddUser_POST.Processor, kwargs['proc'])
        yield xhtml.p(class_ = 'notice')[ message ]
        yield self.presentForm(proc.args, **kwargs)

class UserTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, **kwargs: object) -> Iterator[Tuple[str, XMLContent]]:
        yield 'User name', textInput(name = 'user')
        yield 'Role', dropDownList(name = 'role')[ UIRoleNames ]

class ReqPasswordTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, **kwargs: object) -> Iterator[Tuple[str, XMLContent]]:
        yield 'Operator password', passwordInput(name = 'loginpass')

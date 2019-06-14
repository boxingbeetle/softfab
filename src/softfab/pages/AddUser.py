# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import Iterator, Optional, Tuple

from twisted.cred.error import LoginFailed
from twisted.internet.defer import inlineCallbacks

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, PresentableError, ProcT, Redirect
from softfab.formlib import (
    FormTable, actionButtons, dropDownList, emptyOption, hiddenInput, makeForm,
    passwordInput, textInput
)
from softfab.pageargs import ArgsT, EnumArg, PageArgs, RefererArg, StrArg
from softfab.request import Request
from softfab.userlib import (
    PasswordMessage, User, addUserAccount, authenticateUser, checkPrivilege,
    passwordQuality
)
from softfab.userview import (
    LoginPassArgs, UIRoleNames, passwordStr, uiRoleToSet
)
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

    def presentContent(self, proc: ProcT) -> XMLContent:
        raise NotImplementedError

    def presentForm(self,
            proc: ProcT, prefill: Optional[PageArgs]
            ) -> XMLContent:
        return makeForm(args = prefill)[
            self.__presentFormBody(proc.user)
            ].present(proc=proc)

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
        def process(self, req, user):
            pass

    def presentContent(self, proc: Processor) -> XMLContent:
        yield self.presentForm(proc, None)

class AddUser_POST(AddUserBase['AddUser_POST.Processor',
                               'AddUser_POST.Arguments']):

    class Arguments(AddUser_GET.Arguments, LoginPassArgs):
        action = EnumArg(Actions)
        user = StrArg()
        role = EnumArg(UIRoleNames, None)
        password = StrArg()
        password2 = StrArg()

    class Processor(PageProcessor['AddUser_POST.Arguments']):

        @inlineCallbacks
        def process(self, req, user):
            if req.args.action is Actions.CANCEL:
                raise Redirect(self.page.getCancelURL(req.args))
            elif req.args.action is Actions.ADD:
                # Validate input.
                userName = req.args.user
                if not userName:
                    raise PresentableError('User name cannot be empty.')
                role = req.args.role
                if role is None:
                    # Not all browsers implement the 'required' attribute.
                    raise PresentableError('No role assigned.')

                password = req.args.password
                if password == req.args.password2:
                    quality = passwordQuality(userName, password)
                else:
                    quality = PasswordMessage.MISMATCH
                if quality is not PasswordMessage.SUCCESS:
                    raise PresentableError(passwordStr[quality])

                # Authentication of currently logged-in operator
                reqUserName = user.name
                if reqUserName is not None:
                    try:
                        user_ = yield authenticateUser(
                            reqUserName, req.args.loginpass
                            )
                    except LoginFailed as ex:
                        raise PresentableError(
                            'Operator authentication failed%s.' % (
                                ': ' + str(ex) if str(ex) else ''
                                )
                            )

                # Create new user account.
                try:
                    addUserAccount(
                        userName, password, uiRoleToSet(role)
                        )
                except ValueError as ex:
                    raise PresentableError('%s.' % str(ex))
            else:
                assert False, req.args.action

    def presentContent(self, proc: Processor) -> XMLContent:
        yield xhtml.p[ xhtml.b[
            'User "%s" has been added successfully.' % proc.args.user
            ] ]
        yield xhtml.p[
            'You can use the form below to add another user, or ',
            xhtml.a(href = self.getCancelURL(proc.args))[
                'go back to the users overview page'
                ], '.'
            ]
        yield self.presentForm(proc, LoginPassArgs.subset(proc.args))

    def presentError(self, proc: Processor, message: XML) -> XMLContent:
        yield xhtml.p(class_ = 'notice')[ message ]
        yield self.presentForm(proc, proc.args)

class UserTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, **kwargs: object) -> Iterator[Tuple[str, XMLContent]]:
        yield 'User name', textInput(name = 'user')
        yield 'Role', dropDownList(name = 'role', required = True)[
            emptyOption[ '(not set)' ], UIRoleNames
            ]
        yield 'New password', passwordInput(name = 'password')
        yield 'New password (again)', passwordInput(name = 'password2')

class ReqPasswordTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, **kwargs: object) -> Iterator[Tuple[str, XMLContent]]:
        yield 'Operator password', passwordInput(name = 'loginpass')

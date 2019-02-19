# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.formlib import (
    FormTable, actionButtons, dropDownList, emptyOption, hiddenInput,
    makeForm, passwordInput, textInput
    )
from softfab.pageargs import EnumArg, PageArgs, RefererArg, StrArg
from softfab.userlib import (
    PasswordMessage, addUserAccount, authenticate, passwordQuality
    )
from softfab.userview import (
    LoginPassArgs, UIRoleNames, passwordStr, uiRoleToSet
    )
from softfab.xmlgen import xhtml

from twisted.cred import error
from twisted.internet import defer

from enum import Enum

Actions = Enum('Actions', 'ADD CANCEL')

class AddUser_GET(FabPage):
    icon = 'AddUser1'
    description = 'Add User'

    def checkAccess(self, req):
        req.checkPrivilege('u/c', 'add new users')

    class Arguments(PageArgs):
        indexQuery = RefererArg('UserList')

    class Processor(PageProcessor):
        def process(self, req):
            pass

    def iterStyleDefs(self):
        yield 'td.formlabel { width: 16em; }'

    def presentContent(self, proc):
        yield self.presentForm(proc, None)

    def presentForm(self, proc, prefill):
        return makeForm(args = prefill)[
            self.presentFormBody(proc.req)
            ].present(proc=proc)

    def presentFormBody(self, req):
        yield xhtml.p[ 'Enter information about new user:' ]
        yield UserTable.instance
        if req.getUserName() is None:
            yield hiddenInput(name='loginpass', value='')
        else:
            yield xhtml.p[
                'To verify your identity, '
                'please also enter your own password:'
                ]
            yield ReqPasswordTable.instance
        yield xhtml.p[ actionButtons(Actions) ]

class AddUser_POST(AddUser_GET):

    class Arguments(AddUser_GET.Arguments, LoginPassArgs):
        action = EnumArg(Actions)
        user = StrArg()
        role = EnumArg(UIRoleNames, None)
        password = StrArg()
        password2 = StrArg()

    class Processor(PageProcessor):

        @defer.inlineCallbacks
        def process(self, req):
            if req.args.action is Actions.CANCEL:
                raise Redirect(self.page.getCancelURL(req))
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
                reqUserName = req.getUserName()
                if reqUserName is not None:
                    try:
                        user_ = yield authenticate(
                            reqUserName, req.args.loginpass
                            )
                    except error.LoginFailed as ex:
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

    def getCancelURL(self, req):
        return req.args.refererURL or self.getParentURL(req)

    def presentContent(self, proc):
        yield xhtml.p[ xhtml.b[
            'User "%s" has been added successfully.' % proc.args.user
            ] ]
        yield xhtml.p[
            'You can use the form below to add another user, or ',
            xhtml.a(href = self.getCancelURL(proc.req))[
                'go back to the users overview page'
                ], '.'
            ]
        yield self.presentForm(proc, LoginPassArgs.subset(proc.args))

    def presentError(self, proc, message):
        yield xhtml.p(class_ = 'notice')[ message ]
        yield self.presentForm(proc, proc.args)

class UserTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, proc):
        yield 'User name', textInput(name = 'user')
        yield 'Role', dropDownList(name = 'role', required = True)[
            emptyOption[ '(not set)' ], UIRoleNames
            ]
        yield 'New password', passwordInput(name = 'password')
        yield 'New password (again)', passwordInput(name = 'password2')

class ReqPasswordTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, proc):
        yield 'Operator password', passwordInput(name = 'loginpass')

# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.config import enableSecurity
from softfab.formlib import FormTable, actionButtons, makeForm, passwordInput
from softfab.pageargs import EnumArg, PasswordArg, RefererArg
from softfab.userlib import (
    PasswordMessage, authenticate, changePassword, passwordQuality, userDB
    )
from softfab.userview import LoginPassArgs, PasswordMsgArgs, passwordStr
from softfab.webgui import pageURL
from softfab.xmlgen import xhtml

from twisted.cred import error
from twisted.internet import defer

from enum import Enum


def presentForm(proc):
    return makeForm(args = proc.args)[
        xhtml.p[
            'Please enter a new password for user ',
            xhtml.b[ proc.args.user ], ':'
            ],
        NewPasswordTable.instance,
        xhtml.p[
            'To verify your identity, '
            'please also enter your %s password:' % (
                'old' if proc.args.user == proc.req.getUserName() else 'own'
                )
            ],
        ReqPasswordTable.instance,
        xhtml.p[ actionButtons(Actions) ],
        ].present(proc=proc)

class NewPasswordTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, proc):
        yield 'New password', passwordInput(name = 'password')
        yield 'New password (again)', passwordInput(name = 'password2')

class ReqPasswordTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, proc):
        userName = proc.args.user
        reqUserName = proc.req.getUserName()
        reqPasswordLabel = '%s password' % (
            'Old' if userName == reqUserName else 'Operator'
            )
        yield reqPasswordLabel, passwordInput(name = 'loginpass')

Actions = Enum('Actions', 'CHANGE CANCEL')

class ChangePassword_GET(FabPage):
    icon = 'UserList1'
    description = 'Change Password'
    isActive = staticmethod(lambda: enableSecurity)

    class Arguments(PasswordMsgArgs):
        indexQuery = RefererArg('UserList')
        detailsQuery = RefererArg('UserDetails')

    class Processor(PageProcessor):

        def process(self, req):
            # Validate input.
            userName = req.args.user
            reqUserName = req.getUserName() # get current logged-in user
            if userName == reqUserName:
                req.checkPrivilege('u/mo',
                    'change your password (ask an operator)'
                    )
            else:
                req.checkPrivilege('u/m',
                    "change other user's password (ask an operator)"
                    )

            # Check if userName exists in the userDB.
            if userName not in userDB:
                self.retry = False # pylint: disable=attribute-defined-outside-init
                raise PresentableError(
                    'User "%s" does not exist (anymore)' % userName
                    )

            # Check if msg has been set and act upon accordingly
            msg = req.args.msg
            if msg is not None:
                self.retry = msg is not PasswordMessage.SUCCESS # pylint: disable=attribute-defined-outside-init
                raise PresentableError(passwordStr[msg])

    def checkAccess(self, req):
        # Processor checks privileges.
        pass

    def iterStyleDefs(self):
        yield 'td.formlabel { width: 16em; }'

    def presentContent(self, proc):
        return presentForm(proc)

    def presentError(self, proc, message):
        yield xhtml.p(class_ = 'notice')[ message ]
        if proc.retry:
            yield presentForm(proc)
        else:
            yield self.backToReferer(proc.req)


class ChangePassword_POST(FabPage):
    # Icon is determined by the GET variant of the page.
    # TODO: This asymmetry isn't good.
    #       Either give treat both the GET and POST handlers as full pages
    #       with their own icon etc (see FabPage.__pageInfo), or move the
    #       icon etc. to a per-module container.
    icon = None
    description = 'Change Password'

    class Arguments(ChangePassword_GET.Arguments, LoginPassArgs):
        action = EnumArg(Actions)
        password = PasswordArg(None)
        password2 = PasswordArg(None)

    class Processor(PageProcessor):

        @defer.inlineCallbacks
        def process(self, req):
            if req.args.action is Actions.CANCEL:
                raise Redirect(self.page.getCancelURL(req))
            elif req.args.action is Actions.CHANGE:
                # Validate input.
                userName = req.args.user
                reqUserName = req.getUserName() # get current logged-in user
                if userName == reqUserName:
                    req.checkPrivilege('u/mo',
                        'change your password (ask an operator)'
                        )
                else:
                    req.checkPrivilege('u/m',
                        "change other user's password (ask an operator)"
                        )

                try:
                    userInfo = userDB[userName]
                except KeyError:
                    self.retry = False # pylint: disable=attribute-defined-outside-init
                    raise PresentableError(
                        'User "%s" does not exist (anymore)' % userName
                        )

                password = req.args.password
                if password == req.args.password2:
                    quality = passwordQuality(userName, password)
                else:
                    quality = PasswordMessage.MISMATCH
                if quality is not PasswordMessage.SUCCESS:
                    self.retry = True # pylint: disable=attribute-defined-outside-init
                    raise PresentableError(passwordStr[quality])

                loginpass = req.args.loginpass
                try:
                    user_ = yield authenticate(reqUserName, loginpass)
                except error.LoginFailed as ex:
                    self.retry = True # pylint: disable=attribute-defined-outside-init
                    raise PresentableError(
                        'Verification of %s password failed%s.' % (
                            'old' if userName == reqUserName else 'operator',
                            ': ' + str(ex) if str(ex) else ''
                            )
                        )

                # Apply changes.
                try:
                    changePassword(userInfo, password)
                except ValueError as ex:
                    # Failed to changePassword
                    self.retry = True # pylint: disable=attribute-defined-outside-init
                    raise PresentableError(str(ex))
                else:
                    # Successfully changed password
                    raise Redirect(pageURL(
                        'ChangePassword',
                        PasswordMsgArgs(
                            user = userName, msg = PasswordMessage.SUCCESS
                            )
                        ))
            else:
                assert False, req.args.action

    def checkAccess(self, req):
        # Processor checks privs
        pass

    def getCancelURL(self, req):
        return req.args.refererURL or self.getParentURL(req)

    def presentError(self, proc, message):
        yield xhtml.p(class_ = 'notice')[ message ]
        if proc.retry:
            yield presentForm(proc)
        else:
            yield self.backToReferer(proc.req)

    def presentContent(self, proc):
        assert False
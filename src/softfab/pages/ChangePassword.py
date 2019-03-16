# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum

from twisted.cred.error import LoginFailed
from twisted.internet.defer import inlineCallbacks

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.formlib import (
    FormTable, actionButtons, hiddenInput, makeForm, passwordInput
)
from softfab.pageargs import EnumArg, PasswordArg, RefererArg
from softfab.userlib import (
    PasswordMessage, authenticate, changePassword, passwordQuality, userDB
)
from softfab.userview import LoginPassArgs, PasswordMsgArgs, passwordStr
from softfab.webgui import pageURL
from softfab.xmlgen import XMLContent, xhtml


def presentForm(proc):
    return makeForm(args = proc.args)[
        presentFormBody(proc)
        ].present(proc=proc)

def presentFormBody(proc):
    yield xhtml.p[
        'Please enter a new password for user ', xhtml.b[ proc.args.user ], ':'
        ]
    yield NewPasswordTable.instance
    if proc.req.userName is None:
        yield hiddenInput(name='loginpass', value='')
    else:
        yield xhtml.p[
            'To verify your identity, '
            'please also enter your %s password:' % (
                'old' if proc.args.user == proc.req.userName else 'own'
                )
            ]
        yield ReqPasswordTable.instance
    yield xhtml.p[ actionButtons(Actions) ]

class NewPasswordTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, proc):
        yield 'New password', passwordInput(name = 'password')
        yield 'New password (again)', passwordInput(name = 'password2')

class ReqPasswordTable(FormTable):
    labelStyle = 'formlabel'

    def iterFields(self, proc):
        userName = proc.args.user
        reqUserName = proc.req.userName
        reqPasswordLabel = '%s password' % (
            'Old' if userName == reqUserName else 'Operator'
            )
        yield reqPasswordLabel, passwordInput(name = 'loginpass')

Actions = Enum('Actions', 'CHANGE CANCEL')

class ChangePassword_GET(FabPage['ChangePassword_GET.Processor', 'ChangePassword_GET.Arguments']):
    icon = 'UserList1'
    description = 'Change Password'

    class Arguments(PasswordMsgArgs):
        indexQuery = RefererArg('UserList')
        detailsQuery = RefererArg('UserDetails')

    class Processor(PageProcessor):

        def process(self, req):
            # Validate input.
            userName = req.args.user
            reqUserName = req.userName # get current logged-in user
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

    def presentContent(self, proc: Processor) -> XMLContent:
        return presentForm(proc)

    def presentError(self, proc: Processor, message: str) -> XMLContent:
        yield xhtml.p(class_ = 'notice')[ message ]
        if proc.retry:
            yield presentForm(proc)
        else:
            yield self.backToReferer(proc.req)


class ChangePassword_POST(FabPage['ChangePassword_POST.Processor', 'ChangePassword_POST.Arguments']):
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

        @inlineCallbacks
        def process(self, req):
            if req.args.action is Actions.CANCEL:
                raise Redirect(self.page.getCancelURL(req))
            elif req.args.action is Actions.CHANGE:
                # Validate input.
                userName = req.args.user
                reqUserName = req.userName # get current logged-in user
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

                if reqUserName is not None:
                    try:
                        user_ = yield authenticate(
                            reqUserName, req.args.loginpass
                            )
                    except LoginFailed as ex:
                        self.retry = True # pylint: disable=attribute-defined-outside-init
                        raise PresentableError(
                            'Verification of %s password failed%s.' % (
                                'old' if userName == reqUserName
                                    else 'operator',
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

    def presentError(self, proc: Processor, message: str) -> XMLContent:
        yield xhtml.p(class_ = 'notice')[ message ]
        if proc.retry:
            yield presentForm(proc)
        else:
            yield self.backToReferer(proc.req)

    def presentContent(self, proc: Processor) -> XMLContent:
        assert False

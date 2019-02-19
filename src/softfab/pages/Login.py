# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import FabResource, PageProcessor, PresentableError, Redirect
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.formlib import (
    FormTable, makeForm, passwordInput, submitButton, textInput
    )
from softfab.pageargs import ArgsCorrected, PageArgs, StrArg
from softfab.userlib import (
    IUser, PasswordMessage, authenticate, passwordQuality
    )
from softfab.userview import LoginPassArgs, PasswordMsgArgs
from softfab.webgui import pageURL
from softfab.xmlgen import xhtml

from twisted.cred import error
from twisted.internet import defer


class LoginTable(FormTable):

    def iterFields(self, proc):
        yield 'User name', textInput(name = 'loginname')
        yield 'Password', passwordInput(name = 'loginpass')

class Login_GET(UIPage, FabResource):
    '''Page that presents login form.
    '''
    authenticator = NoAuthPage

    class Arguments(PageArgs):
        url = StrArg(None)

    class Processor(PageProcessor):

        def process(self, req):
            url = req.args.url
            if url is not None and '/' in url:
                # Only accept relative URLs.
                raise ArgsCorrected(req.args, url = None)

    def checkAccess(self, req):
        pass

    def fabTitle(self, proc):
        return 'Log In'

    def presentContent(self, proc):
        yield makeForm(args = proc.args)[
            LoginTable.instance,
            xhtml.p[ submitButton[ 'Log In' ] ]
            ].present(proc=proc)

        userAgent = proc.req.userAgent
        if userAgent.family == 'MSIE':
            version = userAgent.version
            if version and version[0] < 11:
                yield xhtml.p[
                    'Internet Explorer %d is ' % version[0],
                    xhtml.b['not supported'], ' by SoftFab. ',
                    'Please upgrade to ',
                    xhtml.a(href = _downloadURLs['MSIE'], target = '_blank')[
                        'Internet Explorer 11'
                        ], ' or to an alternative browser such as ',
                    xhtml.a(href = _downloadURLs['Mozilla'], target = '_blank')[
                        'Mozilla Firefox'
                        ], ' or ',
                    xhtml.a(href = _downloadURLs['Chrome'], target = '_blank')[
                        'Google Chrome'
                        ], '.'
                    ]
                yield xhtml.p[
                    'You are free to log in anyway, but it is likely you will '
                    'see rendering errors and you might encounter problems '
                    'with JavaScript.'
                    ]

_downloadURLs = {
    'MSIE':
        'https://support.microsoft.com/en-us/products/internet-explorer',
    'Mozilla':
        'https://www.mozilla.com/firefox/',
    'Chrome':
        'https://www.google.com/chrome/',
    }

class Login_POST(Login_GET):
    '''Page that handles submitted login form.
    '''
    authenticator = NoAuthPage

    class Arguments(Login_GET.Arguments, LoginPassArgs):
        loginname = StrArg()

    class Processor(Login_GET.Processor):

        @defer.inlineCallbacks
        def process(self, req):
            super().process(req)

            username = req.args.loginname
            password = req.args.loginpass

            try:
                user = yield authenticate(username, password)
            except error.LoginFailed:
                raise PresentableError('Login failed')
            else:
                # Inactive users are not allowed to log in.
                if not user.isActive():
                    raise PresentableError('User account inactive')
                # Remember logged in user.
                # Starting a new session after login blocks session fixation
                # attacks that inject a valid session cookie that was
                # generated for a different client.
                #   http://en.wikipedia.org/wiki/Session_fixation
                session = req.startSession()
                session.setComponent(IUser, user)

                if passwordQuality(username, password) is not \
                        PasswordMessage.SUCCESS and user.hasPrivilege('u/mo'):
                    # Suggest the user to pick a stronger password.
                    raise Redirect(pageURL(
                        'ChangePassword',
                        PasswordMsgArgs(
                            user = username,
                            msg = PasswordMessage.POOR
                            )
                        ))
                else:
                    url = req.args.url
                    raise Redirect('Home' if url is None else url)

    def presentError(self, proc, message):
        yield xhtml.p(class_ = 'notice')[ message ]
        yield self.presentContent(proc)

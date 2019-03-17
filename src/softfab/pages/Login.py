# SPDX-License-Identifier: BSD-3-Clause

from twisted.cred.error import LoginFailed
from twisted.internet.defer import inlineCallbacks

from softfab.Page import (
    ArgT, FabResource, PageProcessor, PresentableError, ProcT, Redirect
)
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.formlib import (
    FormTable, makeForm, passwordInput, submitButton, textInput
)
from softfab.pageargs import ArgsCorrected, StrArg
from softfab.pagelinks import URLArgs
from softfab.userlib import (
    IUser, PasswordMessage, authenticate, passwordQuality
)
from softfab.userview import LoginPassArgs, PasswordMsgArgs
from softfab.webgui import pageURL
from softfab.xmlgen import XMLContent, xhtml


class LoginTable(FormTable):

    def iterFields(self, proc):
        yield 'User name', textInput(name = 'loginname')
        yield 'Password', passwordInput(name = 'loginpass')

class LoginBase(UIPage[ProcT], FabResource[ArgT, ProcT]):
    authenticator = NoAuthPage
    secureCookie = True

    def checkAccess(self, user: IUser) -> None:
        pass

    def pageTitle(self, proc: ProcT) -> str:
        return 'Log In'

    def presentContent(self, proc: ProcT) -> XMLContent:
        if self.secureCookie and not proc.req.secure:
            yield xhtml.p(class_='notice')[
                'Login is not possible over insecure channel.'
                ]
            yield xhtml.p[
                'Please connect over HTTPS instead.'
                ]
        else:
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

class Login_GET(LoginBase['Login_GET.Processor', 'Login_GET.Arguments']):
    '''Page that presents login form.
    '''

    class Arguments(URLArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            url = req.args.url
            if url is not None and '/' in url:
                # Only accept relative URLs.
                raise ArgsCorrected(req.args, url = None)

_downloadURLs = {
    'MSIE':
        'https://support.microsoft.com/en-us/products/internet-explorer',
    'Mozilla':
        'https://www.mozilla.com/firefox/',
    'Chrome':
        'https://www.google.com/chrome/',
    }

class Login_POST(LoginBase['Login_POST.Processor', 'Login_POST.Arguments']):
    '''Page that handles submitted login form.
    '''

    class Arguments(Login_GET.Arguments, LoginPassArgs):
        loginname = StrArg()

    class Processor(Login_GET.Processor):

        @inlineCallbacks
        def process(self, req):
            super().process(req)

            username = req.args.loginname
            password = req.args.loginpass

            try:
                user = yield authenticate(username, password)
            except LoginFailed:
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
                session = req.startSession(self.page.secureCookie)
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

    def presentError(self, proc: Processor, message: str) -> XMLContent:
        yield xhtml.p(class_ = 'notice')[ message ]
        yield self.presentContent(proc)

# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import FabResource, PageProcessor, Redirect
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.pageargs import ArgsCorrected
from softfab.pagelinks import URLArgs
from softfab.webgui import pageLink
from softfab.xmlgen import XMLContent, xhtml


class Logout_GET(UIPage['Logout_GET.Processor'],
                 FabResource['Logout_GET.Arguments', 'Logout_GET.Processor']):
    '''Page that logs out the user that requests it.
    '''
    authenticator = NoAuthPage

    class Arguments(URLArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            url = req.args.url
            if url is not None and '/' in url:
                # Only accept relative URLs.
                raise ArgsCorrected(req.args, url=None)

            loggedOut = req.stopSession()
            # pylint: disable=attribute-defined-outside-init
            self.loggedOut = loggedOut

            # If the user still has privileges when logged out, redirect to
            # where they logged out from.
            # The privilege we check is semi-arbitrary: listing jobs is needed
            # to see the Home page, so even guests have this privilege.
            if req.user.hasPrivilege('j/l'):
                raise Redirect('Home' if url is None else url)

    def checkAccess(self, req):
        pass

    def pageTitle(self, proc: Processor) -> str:
        return 'Log Out'

    def presentContent(self, proc: Processor) -> XMLContent:
        return (
            xhtml.p[
                'You have been logged out.'
                if proc.loggedOut else
                'You were not logged in.'
                ],
            xhtml.p[ pageLink('Login', proc.args)[ 'Log in' ] ]
            )

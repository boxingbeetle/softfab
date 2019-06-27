# SPDX-License-Identifier: BSD-3-Clause

from typing import cast
from urllib.parse import urljoin

from softfab.Page import FabResource, PageProcessor, Redirect
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.config import rootURL
from softfab.pageargs import ArgsCorrected
from softfab.pagelinks import URLArgs
from softfab.projectlib import project
from softfab.request import Request, relativeURL
from softfab.userlib import User
from softfab.webgui import pageLink
from softfab.xmlgen import XMLContent, xhtml


class Logout_GET(UIPage['Logout_GET.Processor'],
                 FabResource['Logout_GET.Arguments', 'Logout_GET.Processor']):
    '''Page that logs out the user that requests it.
    '''
    authenticator = NoAuthPage.instance

    class Arguments(URLArgs):
        pass

    class Processor(PageProcessor['Logout_GET.Arguments']):

        def process(self,
                    req: Request['Logout_GET.Arguments'],
                    user: User
                    ) -> None:
            url = req.args.url
            if url is not None:
                # Only accept relative URLs.
                url = relativeURL(urljoin(rootURL, url))
                if url is None:
                    raise ArgsCorrected(req.args, url=None)

            loggedOut = req.stopSession()
            # pylint: disable=attribute-defined-outside-init
            self.loggedOut = loggedOut

            # If the user still has privileges when logged out, redirect to
            # where they logged out from.
            # The privilege we check is semi-arbitrary: listing jobs is needed
            # to see the Home page, so even guests have this privilege.
            if project.defaultUser.hasPrivilege('j/l'):
                raise Redirect('Home' if url is None else url)

    def checkAccess(self, user: User) -> None:
        pass

    def pageTitle(self, proc: Processor) -> str:
        return 'Log Out'

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(Logout_GET.Processor, kwargs['proc'])
        return (
            xhtml.p[
                'You have been logged out.'
                if proc.loggedOut else
                'You were not logged in.'
                ],
            xhtml.p[ pageLink('Login', proc.args)[ 'Log in' ] ]
            )

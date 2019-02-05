# SPDX-License-Identifier: BSD-3-Clause

from Page import FabResource, PageProcessor, Redirect
from UIPage import UIPage
from authentication import NoAuthPage
from config import enableSecurity
from xmlgen import xhtml

class Logout(UIPage, FabResource):
    '''Page that logs out the user that requests it.
    '''
    authenticationWrapper = NoAuthPage

    class Processor(PageProcessor):

        def process(self, req):
            if not enableSecurity:
                raise Redirect('Home')
            loggedOut = req.stopSession()
            # pylint: disable=attribute-defined-outside-init
            self.loggedOut = loggedOut

    def checkAccess(self, req):
        pass

    def fabTitle(self, proc):
        return 'Log Out'

    def presentContent(self, proc):
        return (
            xhtml.p[
                'You have been logged out.'
                if proc.loggedOut else
                'You were not logged in.'
                ],
            xhtml.p[ xhtml.a(href = 'Login')[ 'Log in' ] ]
            )

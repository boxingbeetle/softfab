# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import FabResource, PageProcessor
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.xmlgen import xhtml

class Logout(UIPage, FabResource):
    '''Page that logs out the user that requests it.
    '''
    authenticationWrapper = NoAuthPage

    class Processor(PageProcessor):

        def process(self, req):
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

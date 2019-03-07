# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import FabResource, PageProcessor
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.webgui import unorderedList
from softfab.xmlgen import xhtml

class _StartupMessages:

    def __init__(self):
        self.__messages = [ 'Server startup initiated' ]

    def __iter__(self):
        return iter(self.__messages)

    def addMessage(self, message):
        self.__messages.append(message)

    def replaceMessage(self, message):
        self.__messages[-1] = message

startupMessages = _StartupMessages()

# TODO: It would be better to show the splash page only for existing pages
#       and only to authenticated users. However, currently page registration
#       is done after loading databases, because module-level objects will
#       be making database requests.
class SplashPage(UIPage[PageProcessor], FabResource[PageProcessor]):
    authenticator = NoAuthPage

    def checkAccess(self, req):
        pass

    def pageTitle(self, proc):
        return 'Startup in Progress'

    def writeHTTPHeaders(self, response):
        # Service unavailable.
        response.setStatus(503)
        # Retry in N seconds.
        # It seems none of today's browsers honor Retry-After, but Refresh
        # seems to work everywhere.
        retryDelay = 3
        response.setHeader('Retry-After', str(retryDelay))
        response.setHeader('Refresh', str(retryDelay))

        super().writeHTTPHeaders(response)

    def presentContent(self, proc):
        return (
            xhtml.h2[ 'Server starting:' ],
            unorderedList[ startupMessages ]
            )

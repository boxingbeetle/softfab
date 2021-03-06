# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.Page import FabResource, PageProcessor
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.response import ResponseHeaders
from softfab.userlib import User
from softfab.webgui import unorderedList
from softfab.xmlgen import XMLContent, xhtml


class _StartupMessages:

    def __init__(self) -> None:
        super().__init__()
        self.__messages = [ 'Server startup initiated' ]

    def __iter__(self) -> Iterator[str]:
        return iter(self.__messages)

    def addMessage(self, message: str) -> None:
        self.__messages.append(message)

    def replaceMessage(self, message: str) -> None:
        self.__messages[-1] = message

startupMessages = _StartupMessages()

# TODO: It would be better to show the splash page only for existing pages
#       and only to authenticated users. However, currently page registration
#       is done after loading databases, because module-level objects will
#       be making database requests.
class SplashPage(UIPage[PageProcessor],
                 FabResource[FabResource.Arguments, PageProcessor]):
    authenticator = NoAuthPage.instance

    def checkAccess(self, user: User) -> None:
        pass

    def pageTitle(self, proc: PageProcessor) -> str:
        return 'Startup in Progress'

    def writeHTTPHeaders(self, response: ResponseHeaders) -> None:
        # Service unavailable.
        response.setStatus(503)
        # Retry in N seconds.
        # It seems none of today's browsers honor Retry-After, but Refresh
        # seems to work everywhere.
        retryDelay = 3
        response.setHeader('Retry-After', str(retryDelay))
        response.setHeader('Refresh', str(retryDelay))

        super().writeHTTPHeaders(response)

    def presentContent(self, **kwargs: object) -> XMLContent:
        return (
            xhtml.h3[ 'Server starting:' ],
            unorderedList[ startupMessages ].present(**kwargs)
            )

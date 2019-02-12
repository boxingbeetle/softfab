# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import PageProcessor
from softfab.UIPage import UIPage
from softfab.webgui import docLink
from softfab.xmlgen import xhtml

class InternalErrorPage(UIPage, PageProcessor):
    '''500 error page: shown when an internal error occurred.
    '''

    def __init__(self, req, messageText):
        PageProcessor.__init__(self, req)
        UIPage.__init__(self)
        self.__messageText = messageText

    def fabTitle(self, proc):
        return 'Internal Error'

    def writeHTTPHeaders(self, response):
        response.setStatus(500, self.__messageText)
        UIPage.writeHTTPHeaders(self, response)

    def presentContent(self, proc):
        return (
            xhtml.p[ 'Internal error: %s.' % self.__messageText ],
            xhtml.p[ 'Please ', docLink('/reference/contact/')[
                'report this as a bug' ], '.' ]
            )

# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import ProcT, Responder, logPageException
from softfab.StyleResources import styleRoot
from softfab.pagelinks import createUserDetailsLink, loginURL, logoutURL
from softfab.projectlib import project
from softfab.response import Response
from softfab.timelib import getTime
from softfab.timeview import formatTime
from softfab.version import version
from softfab.xmlgen import XMLContent, xhtml

from traceback import TracebackException
from typing import Generic

_logoIcon = styleRoot.addIcon('SoftFabLogo')
_shortcutIcon = styleRoot.addShortcutIcon('SoftFabIcon')

def _createStyleSheets():
    yield styleRoot.addStyleSheet('sw-factory')
_styleSheets = tuple(_createStyleSheets())
# This sheet contains workarounds for the very limited CSS support in MSOffice.
# For example it is used to correct the Atom feed rendering in MS Outlook.
_msOfficeSheet = styleRoot.addStyleSheet('msoffice')
def iterStyleSheets(proc):
    yield from _styleSheets
    if proc.req.userAgent.family == 'MSOffice':
        yield _msOfficeSheet

class _ErrorResponder(Responder):

    def __init__(self, page, ex):
        Responder.__init__(self)
        self.__page = page
        self.__exception = ex

    def respond(self, response, proc):
        response.setStatus(500, 'Unexpected exception processing request')
        proc.processingError = self.__exception
        self.__page.respond(response, proc)

class UIPage(Responder, Generic[ProcT]):

    def respond(self, response, proc):
        self.writeHTTPHeaders(response)
        self.__writeHTML(response, proc)

    def writeHTTPHeaders(self, response: Response) -> None:
        if response.userAgent.acceptsXHTML:
            # All modern browsers accept the XHTML content type.
            contentType = 'application/xhtml+xml'
        else:
            # Old browsers, in particular IE8 and older, don't accept the
            # XHTML content type, but will parse the document correctly
            # when it is served as HTML.
            contentType = 'text/html'
        response.setHeader('Content-Type', contentType + '; charset=UTF-8')

    def __writeHTML(self, response: Response, proc: ProcT) -> None:
        self.__writeDocType(response)
        response.write(
            xhtml.html(lang = 'en')[
                xhtml.head[ self.presentHeadParts(proc) ],
                xhtml.body[ self.__presentBodyParts(response, proc) ],
                ]
            )

    def __writeDocType(self, response: Response) -> None:
        response.write('<!DOCTYPE html>\n')

    def presentHeadParts(self, proc: ProcT) -> XMLContent:
        yield xhtml.meta(charset='UTF-8')
        yield xhtml.meta(
            name='viewport',
            content='width=device-width, initial-scale=1, minimum-scale=1'
            )
        yield xhtml.title[ '%s - %s' % (project['name'], self.pageTitle(proc)) ]
        for sheet in iterStyleSheets(proc):
            yield sheet.present(proc=proc)
        customStyleDefs = '\n'.join(self.iterStyleDefs())
        if customStyleDefs:
            yield xhtml.style[customStyleDefs]
        yield _shortcutIcon.present(proc=proc)

    def __title(self, proc: ProcT) -> XMLContent:
        return (
            xhtml.span(class_ = 'project')[ project['name'] ],
            xhtml.span(class_ = 'softfab')[ ' SoftFab' ],
            xhtml.span(class_ = 'project')[ ' \u2013 ' ],
            self.pageTitle(proc)
            )

    def pageTitle(self, proc: ProcT) -> str:
        raise NotImplementedError

    def iterStyleDefs(self):
        '''Iterates through page-specific CSS definition strings.
        The default implementation contains no style definitions.
        '''
        return ()

    def errorResponder(self, ex: Exception) -> Responder:
        return _ErrorResponder(self, ex)

    def formatError(self, ex):
        '''Yields HTML informing the user of the given exception.
        '''
        yield xhtml.p(class_ = 'notice')[
            'An error occurred while generating this page.'
            ]
        if self.debugSupport:
            tb = TracebackException.from_exception(ex)
            yield xhtml.pre[tb.format()]
        else:
            yield xhtml.p['Details were written to the server log.']

    def __presentBodyParts(self, response: Response, proc: ProcT) -> XMLContent:
        yield self.presentHeader(proc)
        try:
            yield (
                xhtml.div(class_ = 'body')[ self.__presentBody(proc) ],
                self.presentBackgroundScripts(proc)
                )
        except Exception as ex:
            logPageException(proc.req, 'Error presenting page')
            response.setStatus(500, 'Error presenting page')
            yield from self.formatError(ex)

    def __presentBody(self, proc: ProcT) -> XMLContent:
        if proc.processingError is not None:
            return self.formatError(proc.processingError)
        elif proc.error is not None:
            return self.presentError(proc, proc.error)
        else:
            return self.presentContent(proc)

    def presentHeader(self, proc):
        userName = proc.req.getUserName()
        return xhtml.div(class_ = 'titlebar')[
            xhtml.div(class_ = 'title')[ self.__title(proc) ],
            xhtml.div(class_ = 'info')[
                xhtml.a(href=loginURL(proc.req))[ 'log in' ]
                if userName is None else (
                    createUserDetailsLink(userName), ' \u2013 ',
                    xhtml.a(href=logoutURL(proc.req))[ 'log out' ]
                    ),
                xhtml.br,
                formatTime(getTime())
                ],
            xhtml.div(class_ = 'logo')[
                xhtml.a(href = 'About', title = 'SoftFab %s' % version)[
                    _logoIcon.present(proc=proc)
                    ]
                ]
            ]

    def presentContent(self, proc):
        raise NotImplementedError

    def presentError(self,
            proc: ProcT,
            message: str # pylint: disable=unused-argument
            ) -> XMLContent:
        return message

    def presentBackgroundScripts(self, proc): # pylint: disable=unused-argument
        return None

# SPDX-License-Identifier: BSD-3-Clause

from traceback import TracebackException
from typing import Generic, Iterable, Iterator, Optional, cast

from softfab.Page import ProcT, Responder, logPageException
from softfab.StyleResources import styleRoot
from softfab.pagelinks import createUserDetailsLink, loginURL, logoutURL
from softfab.projectlib import project
from softfab.request import Request
from softfab.response import Response, ResponseHeaders
from softfab.timelib import getTime
from softfab.timeview import formatTime
from softfab.version import VERSION
from softfab.xmlgen import XML, XMLContent, XMLNode, XMLPresentable, xhtml

_logoIcon = styleRoot.addIcon('SoftFabLogo')
_shortcutIcon = styleRoot.addShortcutIcon('SoftFabIcon')

factoryStyleSheet = styleRoot.addStyleSheet('sw-factory')

fixedHeadItems: Iterable[XMLPresentable] = (
    xhtml.meta(charset='UTF-8'),
    factoryStyleSheet,
    xhtml.meta(
        name='viewport',
        content='width=device-width, initial-scale=1, minimum-scale=1'
        ),
    _shortcutIcon
    )

class UIResponder(Responder, Generic[ProcT]):

    def __init__(self, page: 'UIPage[ProcT]', proc: ProcT):
        super().__init__()
        self.page = page
        self.proc = proc

    async def respond(self, response: Response) -> None:
        page = self.page
        proc = self.proc
        page.writeHTTPHeaders(response)
        page.writeHTML(response, proc)

class _ErrorResponder(UIResponder):

    def __init__(self, page: 'UIPage[ProcT]', ex: Exception, proc: ProcT):
        super().__init__(page, proc)
        self.__exception = ex

    async def respond(self, response: Response) -> None:
        response.setStatus(500, 'Unexpected exception processing request')
        self.proc.processingError = self.__exception
        await super().respond(response)

class UIPage(Generic[ProcT]):

    def writeHTTPHeaders(self, response: ResponseHeaders) -> None:
        if response.userAgent.acceptsXHTML:
            # All modern browsers accept the XHTML content type.
            contentType = 'application/xhtml+xml'
        else:
            # Old browsers, in particular IE8 and older, don't accept the
            # XHTML content type, but will parse the document correctly
            # when it is served as HTML.
            contentType = 'text/html'
        response.setContentType(contentType + '; charset=UTF-8')

    def writeHTML(self, response: Response, proc: ProcT) -> None:
        req = proc.req
        ccURL = req.relativeRoot
        presentationArgs = dict(
            proc=proc,
            ccURL=ccURL,
            styleURL=ccURL + styleRoot.relativeURL,
            )
        response.write('<!DOCTYPE html>\n')
        response.writeXML(
            xhtml.html(lang='en')[
                xhtml.head[
                    self.presentHeadParts(**presentationArgs)
                    ],
                xhtml.body[
                    self.__presentBodyParts(req, response, **presentationArgs)
                    ],
                ]
            )

    def presentHeadParts(self, **kwargs: object) -> XMLContent:
        proc = cast(ProcT, kwargs['proc'])
        for item in fixedHeadItems:
            yield item.present(**kwargs)
        yield xhtml.title[ f'{project.name} - {self.pageTitle(proc)}' ]
        customStyleDefs = '\n'.join(self.iterStyleDefs())
        if customStyleDefs:
            yield xhtml.style[customStyleDefs]

    def __title(self, proc: ProcT) -> XMLContent:
        return (
            xhtml.span(class_ = 'project')[ project.name ],
            xhtml.span(class_ = 'softfab')[ ' SoftFab' ],
            xhtml.span(class_ = 'project')[ ' \u2013 ' ],
            self.pageTitle(proc)
            )

    def pageTitle(self, proc: ProcT) -> str:
        raise NotImplementedError

    def iterStyleDefs(self) -> Iterator[str]:
        '''Iterates through page-specific CSS definition strings.
        The default implementation contains no style definitions.
        '''
        return iter(())

    def getResponder(self, path: Optional[str], proc: ProcT) -> Responder:
        if path is None:
            return UIResponder(self, proc)
        else:
            raise KeyError('Page does not contain subitems')

    def errorResponder(self, ex: Exception, proc: ProcT) -> Responder:
        return _ErrorResponder(self, ex, proc)

    def __formatError(self, req: Request, ex: Exception) -> Iterator[XMLNode]:
        '''Yields HTML informing the user of the given exception.
        '''
        yield xhtml.p(class_ = 'notice')[
            'An error occurred while generating this page.'
            ]
        if req.displayTracebacks:
            tb = TracebackException.from_exception(ex)
            yield xhtml.pre[tb.format()]
        else:
            yield xhtml.p['Details were written to the server log.']

    def __presentBodyParts(self,
                           req: Request,
                           response: ResponseHeaders,
                           **kwargs: object
                           ) -> XMLContent:
        proc = cast(ProcT, kwargs['proc'])
        yield self.presentHeader(**kwargs)
        try:
            yield xhtml.div(class_='body')[
                self.__presentBody(req, **kwargs)
                ]
            if proc.processingError is None:
                yield self.presentBackgroundScripts(**kwargs)
        except Exception as ex:
            logPageException(req, 'Error presenting page')
            response.setStatus(500, 'Error presenting page')
            yield from self.__formatError(req, ex)

    def __presentBody(self, req: Request, **kwargs: object) -> XMLContent:
        proc = cast(ProcT, kwargs['proc'])
        if proc.processingError is not None:
            return self.__formatError(req, proc.processingError)
        elif proc.error is not None:
            return self.presentError(proc.error, **kwargs)
        else:
            return self.presentContent(**kwargs)

    def presentHeader(self, **kwargs: object) -> XMLContent:
        proc = cast(ProcT, kwargs['proc'])
        ccURL = cast(str, kwargs['ccURL'])
        userName = proc.user.name
        return xhtml.div(class_ = 'titlebar')[
            xhtml.div(class_ = 'title')[ self.__title(proc) ],
            xhtml.div(class_ = 'info')[
                xhtml.a(href=ccURL + loginURL(proc.req))[ 'log in' ]
                if userName is None else (
                    createUserDetailsLink(userName).present(**kwargs),
                    ' \u2013 ',
                    xhtml.a(href=ccURL + logoutURL(proc.req))[ 'log out' ]
                    ),
                xhtml.br,
                formatTime(getTime())
                ],
            xhtml.div(class_ = 'logo')[
                xhtml.a(href=ccURL + 'About', title=f'SoftFab {VERSION}')[
                    _logoIcon.present(**kwargs)
                    ]
                ]
            ]

    def presentContent(self, **kwargs: object) -> XMLContent:
        raise NotImplementedError

    def presentError(self, # pylint: disable=unused-argument
            message: XML, **kwargs: object
            ) -> XMLContent:
        return message

    def presentBackgroundScripts(self, # pylint: disable=unused-argument
            **kwargs: object
            ) -> XMLContent:
        return None

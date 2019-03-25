# SPDX-License-Identifier: BSD-3-Clause

'''
Module to render the page
'''

from typing import ClassVar, Iterator, Optional, Type, cast

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.interfaces import IProducer, IPullProducer, IPushProducer

from softfab.FabPage import FabPage
from softfab.Page import (
    FabResource, InvalidRequest, PageProcessor, PresentableError, Redirect,
    Redirector, Responder, logPageException
)
from softfab.UIPage import UIPage, UIResponder
from softfab.pageargs import ArgsCorrected, ArgsInvalid, ArgsT, Query, dynamic
from softfab.request import Request
from softfab.response import Response
from softfab.userlib import AccessDenied, User
from softfab.utils import abstract
from softfab.webgui import docLink
from softfab.xmlgen import XMLContent, xhtml

# Profiling options:

# Print the time it took to render the page.
_timeRender = False
# Profile the rendering and create a file with profile data.
# Note that capturing profile data adds considerable overhead, so don't
# attach any value to the absolute times while doing that. The useful
# information is in where most time gets spent relatively.
_profileRender = False

if _timeRender:
    from time import time
if _profileRender:
    from cProfile import Profile

class ErrorPage(UIPage[PageProcessor[ArgsT]], PageProcessor[ArgsT]):
    """Abstract base class for error pages.
    """
    status = abstract # type: ClassVar[int]
    title = abstract # type: ClassVar[str]

    def __init__(self,
                 page: 'FabResource[ArgsT, PageProcessor[ArgsT]]',
                 req: Request[ArgsT],
                 args: ArgsT,
                 user: User,
                 messageText: Optional[str] = None
                 ):
        PageProcessor.__init__(self, page, req, args, user)
        UIPage.__init__(self)

        if messageText is None:
            messageText = self.title
        self.messageText = messageText

    def pageTitle(self, proc: PageProcessor[ArgsT]) -> str:
        return self.title

    def writeHTTPHeaders(self, response: Response) -> None:
        response.setStatus(self.status, self.messageText)
        super().writeHTTPHeaders(response)

    def presentContent(self, proc: PageProcessor[ArgsT]) -> XMLContent:
        raise NotImplementedError

class BadRequestPage(ErrorPage[ArgsT]):
    '''400 error page.
    '''

    status = 400
    title = 'Bad Request'

    def __init__(self,
                 page: 'FabResource[ArgsT, PageProcessor[ArgsT]]',
                 req: Request[ArgsT],
                 args: ArgsT,
                 user: User,
                 messageText: str,
                 messageHTML: XMLContent
                 ):
        ErrorPage.__init__(self, page, req, args, user, messageText)
        self.messageHTML = messageHTML

    def presentContent(self, proc: PageProcessor[ArgsT]) -> XMLContent:
        return self.messageHTML

class ForbiddenPage(ErrorPage[ArgsT]):
    '''403 error page: shown when access is denied.
    '''

    status = 403
    title = 'Access Denied'

    def presentContent(self, proc: PageProcessor[ArgsT]) -> XMLContent:
        return xhtml.p[ 'Access denied: %s.' % self.messageText ]

class NotFoundPage(ErrorPage[ArgsT]):
    '''404 error page.
    TODO: When there is a directory in the URL, the style sheets and images
          are not properly referenced.
    '''

    status = 404
    title = 'Page Not Found'

    def presentContent(self, proc: PageProcessor[ArgsT]) -> XMLContent:
        return (
            xhtml.p[ 'The page you requested was not found on this server.' ],
            xhtml.p[ xhtml.a(href = 'Home')[ 'Back to Home' ] ]
            )

class InternalErrorPage(ErrorPage[ArgsT]):
    '''500 error page: shown when an internal error occurred.
    '''

    status = 500
    title = 'Internal Error'

    def presentContent(self, proc: PageProcessor[ArgsT]) -> XMLContent:
        return (
            xhtml.p[ 'Internal error: %s.' % self.messageText ],
            xhtml.p[ 'Please ', docLink('/reference/contact/')[
                'report this as a bug' ], '.' ]
            )

def _checkActive(
        req: Request[ArgsT],
        page: FabResource[ArgsT, PageProcessor[ArgsT]]
        ) -> None:
    '''If page is not active, redirect to parent.
    '''
    if isinstance(page, FabPage):
        if not page.isActive():
            raise Redirect(page.getParentURL(req))

@inlineCallbacks
def parseAndProcess(page: FabResource[ArgsT, PageProcessor[ArgsT]],
                    req: Request[ArgsT],
                    user: User
                    ) -> Iterator[Deferred]:
    '''Parse step: determine values for page arguments.
    Processing step: database interaction.
    Returns a `Deferred` which has a `Responder` as its result.
    '''
    try:
        # Page-level authorization.
        # It is possible for additional access checks to fail during the
        # processing step.
        page.checkAccess(user)

        # Argument parsing.
        try:
            args = req.parseArgs(cast(Type[ArgsT], page.Arguments))
        except ArgsCorrected as ex:
            if req.method == 'GET':
                raise
            else:
                # We can't correct args using redirection if args may have
                # come from the request body instead of the URL.
                args = cast(ArgsCorrected[ArgsT], ex).correctedArgs
        req.args = args

        _checkActive(req, page)

        # Processing step.
        proc = page.Processor(
            page, req, args, user
            ) # type: PageProcessor[ArgsT]
        try:
            yield proc.process(req, user)
        except PresentableError as ex:
            proc.error = ex.args[0]
        else:
            assert all(
                    value is not dynamic
                    for name_, value in args.items()
                ), 'unhandled dynamic defaults: ' + ', '.join(
                    name
                    for name, value in args.items()
                    if value is dynamic
                )
            proc.processTables()
    except AccessDenied as ex:
        forbiddenPage = ForbiddenPage(
            page, req, args, user,
            "You don't have permission to %s" % (
                str(ex) or 'access this page'
                )
            )
        proc = forbiddenPage
        responder = UIResponder(forbiddenPage, proc) # type: Responder
    except ArgsCorrected as ex:
        subPath = req.getSubPath()
        query = Query.fromArgs(ex.correctedArgs)
        if subPath is None:
            url = '%s?%s' % (page.name, query.toURL())
        else:
            url = '%s/%s?%s' % (page.name, subPath, query.toURL())
        responder = proc = Redirector(req, url)
    except ArgsInvalid as ex:
        # TODO: We don't have an arguments object because we're reporting
        #       that creating one failed.
        args = cast(ArgsT, None)
        badRequestPage = BadRequestPage(
            page, req, args, user,
            str(ex),
            (    xhtml.p[ 'Invalid arguments:' ],
                xhtml.dl[(
                    ( xhtml.dt[ name ], xhtml.dd[ message ] )
                    for name, message in ex.errors.items()
                    )]
                )
            )
        proc = badRequestPage
        responder = UIResponder(badRequestPage, proc)
    except InvalidRequest as ex:
        badRequestPage = BadRequestPage(
            page, req, args, user,
            str(ex),
            xhtml.p[ 'Invalid request: ', str(ex) ]
            )
    except Exception as ex:
        logPageException(req, 'Unexpected exception processing request')
        responder = page.errorResponder(ex, proc)
    else:
        try:
            responder = page.getResponder(req.getSubPath(), proc)
        except KeyError:
            responder = UIResponder(NotFoundPage(page, req, args, user), proc)

    req.processEnd()
    return responder

def present(responder: Responder, response: Response) -> Optional[Deferred]:
    '''Presentation step: write a response based on the processing results.
    Returns None or a Deferred that does the actual presentation.
    '''
    if _timeRender:
        start = time()
    if _profileRender:
        profile = Profile()
        presenter = profile.runcall(responder.respond, response)
        profile.dump_stats('request.prof')
    else:
        presenter = responder.respond(response)
    if _timeRender:
        end = time()
        print('Responding took %1.3f seconds' % (end - start))

    if IProducer.providedBy(presenter):
        # Producer which will write to the request object.
        d = response.registerProducer(presenter)
        if IPushProducer.providedBy(presenter):
            # Note: This only finishes the headers.
            response.finish()
            return d
        elif IPullProducer.providedBy(presenter):
            # We don't actually have any pull producers at the moment.
            # TODO: Decide whether to use pull producers or remove support.
            raise NotImplemented
        else:
            raise TypeError(type(presenter))
    else:
        if isinstance(presenter, Deferred):
            presenter.addCallback(
                lambda result, response: response.finish(),
                response
                )
        elif presenter is None:
            response.finish()
        else:
            assert False, presenter
        return presenter

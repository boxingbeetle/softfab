# SPDX-License-Identifier: BSD-3-Clause

'''
Module to render the page
'''

from typing import Any, ClassVar, Generator, Iterator, Optional, Type, cast
# TODO: we're using both the standard library and Twisted for logging.
#       We should probably just pick one.
import logging

from twisted.cred.error import LoginFailed, Unauthorized
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.error import ConnectionLost
from twisted.internet.interfaces import IProducer, IPushProducer
from twisted.python import log
from twisted.python.failure import Failure
from twisted.web.http import Request as TwistedRequest
from twisted.web.server import NOT_DONE_YET

from softfab.FabPage import FabPage
from softfab.Page import (
    FabResource, InternalError, InvalidRequest, PageProcessor,
    PresentableError, ProcT, Redirect, Redirector, Responder, logPageException
)
from softfab.UIPage import UIPage, UIResponder
from softfab.pageargs import ArgsCorrected, ArgsInvalid, ArgsT, Query, dynamic
from softfab.request import Request
from softfab.response import Response
from softfab.userlib import AccessDenied, UnknownUser, User
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

class ErrorPage(UIPage[ProcT]):
    """Abstract base class for error pages.
    """
    status: ClassVar[int] = abstract
    title: ClassVar[str] = abstract

    def __init__(self, messageText: Optional[str] = None):
        UIPage.__init__(self)

        if messageText is None:
            messageText = self.title
        self.messageText = messageText

    def pageTitle(self, proc: ProcT) -> str:
        return self.title

    def writeHTTPHeaders(self, response: Response) -> None:
        response.setStatus(self.status, self.messageText)
        super().writeHTTPHeaders(response)

    def presentContent(self, **kwargs: object) -> XMLContent:
        raise NotImplementedError

class BadRequestPage(ErrorPage[ProcT]):
    '''400 error page.
    '''

    status = 400
    title = 'Bad Request'

    def __init__(self, messageText: str, messageHTML: XMLContent):
        ErrorPage.__init__(self, messageText)
        self.messageHTML = messageHTML

    def presentContent(self, **kwargs: object) -> XMLContent:
        return self.messageHTML

class ForbiddenPage(ErrorPage[ProcT]):
    '''403 error page: shown when access is denied.
    '''

    status = 403
    title = 'Access Denied'

    def presentContent(self, **kwargs: object) -> XMLContent:
        return xhtml.p[ f'Access denied: {self.messageText}.' ]

class NotFoundPage(ErrorPage[ProcT]):
    '''404 error page.
    TODO: When there is a directory in the URL, the style sheets and images
          are not properly referenced.
    '''

    status = 404
    title = 'Page Not Found'

    def presentContent(self, **kwargs: object) -> XMLContent:
        return (
            xhtml.p[ 'The page you requested was not found on this server.' ],
            xhtml.p[ xhtml.a(href = 'Home')[ 'Back to Home' ] ]
            )

class InternalErrorPage(ErrorPage[ProcT]):
    '''500 error page: shown when an internal error occurred.
    '''

    status = 500
    title = 'Internal Error'

    def presentContent(self, **kwargs: object) -> XMLContent:
        return (
            xhtml.p[ f'Internal error: {self.messageText}.' ],
            xhtml.p[ 'Please ', docLink('/reference/contact/')[
                'report this as a bug' ], '.' ]
            )

class _PlainTextResponder(Responder):

    def __init__(self, status: int, message: str):
        self.__status = status
        self.__message = message

    def respond(self, response: Response) -> None:
        response.setStatus(self.__status, self.__message)
        response.setContentType('text/plain')
        response.write(self.__message + '\n')

def renderAuthenticated(page: FabResource, request: TwistedRequest) -> object:
    def done(result: object) -> None: # pylint: disable=unused-argument
        request.finish()
    def failed(fail: Failure) -> None:
        request.processingFailed(fail)
        # Returning None (implicitly) because the error is handled.
        # Otherwise, it will be logged twice.
    d = renderAsync(page, request)
    d.addCallback(done).addErrback(failed) # pylint: disable=no-member
    return NOT_DONE_YET

@inlineCallbacks
def renderAsync(
        page: FabResource, request: TwistedRequest
        ) -> Generator[Deferred, Any, None]:
    req: Request = Request(request)
    streaming = False
    try:
        authenticator = page.authenticator
        try:
            user: User
            user = yield authenticator.authenticate(req)
        except LoginFailed as ex:
            responder = authenticator.askForAuthentication(
                req, ex.args[0] if ex.args else None
                )
        except Unauthorized as ex:
            responder = _PlainTextResponder(
                403, ex.args[0] if ex.args else
                        'You are not authorized to perform this operation'
                )
        else:
            responder = yield parseAndProcess(page, req, user)
            streaming = page.streaming
    except Redirect as ex:
        responder = Redirector(ex.url)
    except InternalError as ex:
        logging.error(
            'Internal error processing %s: %s', page.name, str(ex)
            )
        responder = UIResponder(
            InternalErrorPage[PageProcessor](str(ex)),
            PageProcessor(page, req, FabResource.Arguments(), UnknownUser())
            )

    response = Response(request, req.userAgent, streaming)
    try:
        yield present(responder, response)
    except ConnectionLost as ex:
        subPath = req.getSubPath()
        log.msg(
            'Connection lost while presenting page %s%s: %s',
            page.name, '' if subPath is None else f' item "{subPath}"', ex
            )

def _checkActive(
        page: FabResource[ArgsT, PageProcessor[ArgsT]],
        args: ArgsT
        ) -> None:
    '''If page is not active, redirect to parent.
    '''
    if isinstance(page, FabPage):
        if not page.isActive():
            raise Redirect(page.getParentURL(args))

@inlineCallbacks
def parseAndProcess(page: FabResource[ArgsT, PageProcessor[ArgsT]],
                    req: Request[ArgsT],
                    user: User
                    ) -> Iterator[Deferred]:
    '''Parse step: determine values for page arguments.
    Processing step: database interaction.
    Returns a `Deferred` which has a `Responder` as its result.
    '''

    # We might hit an error before argument parsing completes, for example
    # if access is denied at the page level or if the argument parsing
    # itself raises an exception.
    # TODO: There should be a way to respond without having a processing
    #       result, or to construct a processing result without arguments.
    args = cast(ArgsT, None)
    # TODO: Create processor in the processing step.
    #       This is currently not possible because the error handlers
    #       need a PageProcessor instance.
    proc: PageProcessor[ArgsT] = page.Processor(page, req, args, user)

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
        proc.args = args

        _checkActive(page, args)

        # Processing step.
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
        forbiddenPage: ErrorPage[PageProcessor[ArgsT]] = ForbiddenPage(
            f"You don't have permission to {str(ex) or 'access this page'}"
            )
        responder: Responder = UIResponder(forbiddenPage, proc)
    except ArgsCorrected as ex:
        subPath = req.getSubPath()
        query = Query.fromArgs(ex.correctedArgs)
        if subPath is None:
            url = f'{page.name}?{query.toURL()}'
        else:
            url = f'{page.name}/{subPath}?{query.toURL()}'
        responder = Redirector(url)
    except ArgsInvalid as ex:
        badRequestPage: ErrorPage[PageProcessor[ArgsT]] = BadRequestPage(
            str(ex),
            (    xhtml.p[ 'Invalid arguments:' ],
                xhtml.dl[(
                    ( xhtml.dt[ name ], xhtml.dd[ message ] )
                    for name, message in ex.errors.items()
                    )]
                )
            )
        responder = UIResponder(badRequestPage, proc)
    except InvalidRequest as ex:
        badRequestPage = BadRequestPage(
            str(ex),
            xhtml.p[ 'Invalid request: ', str(ex) ]
            )
        responder = UIResponder(badRequestPage, proc)
    except Exception as ex:
        logPageException(req, 'Unexpected exception processing request')
        responder = page.errorResponder(ex, proc)
    else:
        try:
            responder = page.getResponder(req.getSubPath(), proc)
        except KeyError:
            notFoundPage: ErrorPage[PageProcessor[ArgsT]] = NotFoundPage(
                    )
            responder = UIResponder(notFoundPage, proc)

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
        else:
            # We don't have any pages implementing IPullProducer.
            raise TypeError(type(presenter))
    else:
        if isinstance(presenter, Deferred):
            presenter.addCallback(response.writeAndFinish)
        elif presenter is None:
            response.finish()
        else:
            assert False, presenter
        return presenter

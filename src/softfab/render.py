# SPDX-License-Identifier: BSD-3-Clause

'''
Module to render the page
'''

from softfab.Page import (
    AccessDenied, InvalidRequest, PageProcessor, PresentableError, Redirect,
    Redirector, logPageException
    )
from softfab.UIPage import UIPage
from softfab.pageargs import ArgsCorrected, ArgsInvalid, dynamic
from softfab.response import Response
from softfab.utils import abstract
from softfab.webgui import docLink
from softfab.xmlgen import XMLContent, xhtml

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.interfaces import IPullProducer, IProducer, IPushProducer

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

class ErrorPage(UIPage[PageProcessor], PageProcessor):
    """Abstract base class for error pages.
    """
    status = abstract
    title = abstract

    def __init__(self, req, messageText=None):
        PageProcessor.__init__(self, req)
        UIPage.__init__(self)

        if messageText is None:
            messageText = self.title
        self.messageText = messageText

    def pageTitle(self, proc: PageProcessor) -> str:
        return self.title

    def writeHTTPHeaders(self, response: Response) -> None:
        response.setStatus(self.status, self.messageText)
        super().writeHTTPHeaders(response)

    def presentContent(self, proc: PageProcessor) -> XMLContent:
        raise NotImplementedError

class BadRequestPage(ErrorPage):
    '''400 error page.
    '''

    status = 400
    title = 'Bad Request'

    def __init__(self, req, messageText, messageHTML):
        ErrorPage.__init__(self, req, messageText)
        self.messageHTML = messageHTML

    def presentContent(self, proc: PageProcessor) -> XMLContent:
        return self.messageHTML

class ForbiddenPage(ErrorPage):
    '''403 error page: shown when access is denied.
    '''

    status = 403
    title = 'Access Denied'

    def presentContent(self, proc: PageProcessor) -> XMLContent:
        return xhtml.p[ 'Access denied: %s.' % self.messageText ]

class NotFoundPage(ErrorPage):
    '''404 error page.
    TODO: When there is a directory in the URL, the style sheets and images
          are not properly referenced.
    '''

    status = 404
    title = 'Page Not Found'

    def presentContent(self, proc: PageProcessor) -> XMLContent:
        return (
            xhtml.p[ 'The page you requested was not found on this server.' ],
            xhtml.p[ xhtml.a(href = 'Home')[ 'Back to Home' ] ]
            )

class InternalErrorPage(ErrorPage):
    '''500 error page: shown when an internal error occurred.
    '''

    status = 500
    title = 'Internal Error'

    def presentContent(self, proc: PageProcessor) -> XMLContent:
        return (
            xhtml.p[ 'Internal error: %s.' % self.messageText ],
            xhtml.p[ 'Please ', docLink('/reference/contact/')[
                'report this as a bug' ], '.' ]
            )

def _checkActive(req, page):
    '''If page is not active, redirect to parent.
    '''
    if hasattr(page, 'isActive'):
        if not page.isActive():
            # Note: The presence of isActive() indicates this is a FabPage,
            #       therefore it will have getParentURL() as well.
            raise Redirect(page.getParentURL(req))

@inlineCallbacks
def parseAndProcess(page, req):
    '''Parse step: determine values for page arguments.
    Processing step: database interaction.
    Returns a Deferred which has a (responder, proc) pair as its result.
    '''
    try:
        # Page-level authorization.
        # It is possible for additional access checks to fail during the
        # processing step.
        page.checkAccess(req)

        # Argument parsing.
        try:
            req._parse(page) # pylint: disable=protected-access
        except ArgsCorrected as ex:
            if req.method == 'GET':
                raise
            else:
                # We can't correct args using redirection if args may have
                # come from the request body instead of the URL.
                req.args = ex.correctedArgs

        _checkActive(req, page)

        # Processing step.
        proc = page.Processor(req)
        proc.page = page
        proc.args = req.args
        try:
            yield proc.process(req)
        except PresentableError as ex:
            proc.error = ex.args[0]
        else:
            assert all(
                    value is not dynamic
                    for name_, value in req.args.items()
                ), 'unhandled dynamic defaults: ' + ', '.join(
                    name
                    for name, value in req.args.items()
                    if value is dynamic
                )
            proc.processTables()
    except AccessDenied as ex:
        responder = proc = ForbiddenPage(
            req,
            "You don't have permission to %s" % (
                str(ex) or 'access this page'
                )
            )
    except ArgsCorrected as ex:
        subPath = req.getSubPath()
        if subPath is None:
            url = page.name + ex.toQuery()
        else:
            url = '%s/%s%s' % ( page.name, subPath, ex.toQuery() )
        responder = proc = Redirector(req, url)
    except ArgsInvalid as ex:
        responder = proc = BadRequestPage(
            req,
            str(ex),
            (    xhtml.p[ 'Invalid arguments:' ],
                xhtml.dl[(
                    ( xhtml.dt[ name ], xhtml.dd[ message ] )
                    for name, message in ex.errors.items()
                    )]
                )
            )
    except InvalidRequest as ex:
        responder = proc = BadRequestPage(
            req,
            str(ex),
            xhtml.p[ 'Invalid request: ', str(ex) ]
            )
    except Exception as ex:
        logPageException(req, 'Unexpected exception processing request')
        responder = page.errorResponder(ex)
    else:
        try:
            responder = page.getResponder(req.getSubPath(), proc)
        except KeyError:
            responder = NotFoundPage(req)

    req.processEnd()
    return (responder, proc)

def present(request, responder, proc):
    '''Presentation step: write a response based on the processing results.
    Returns None or a Deferred that does the actual presentation.
    '''
    streaming = getattr(proc, 'page', None) and proc.page.streaming
    response = Response(request, proc, streaming)
    if _timeRender:
        start = time()
    if _profileRender:
        profile = Profile()
        presenter = profile.runcall(responder.respond, response, proc)
        profile.dump_stats('request.prof')
    else:
        presenter = responder.respond(response, proc)
    if _timeRender:
        end = time()
        print('Responding took %1.3f seconds' % (end - start))

    if IProducer.providedBy(presenter):
        # Producer which will write to the request object.
        d = response.registerProducer(presenter)
        if IPushProducer.providedBy(presenter):
            assert streaming
            # Note: This only finishes the headers.
            response.finish()
            return d
        elif IPullProducer.providedBy(presenter):
            assert not streaming
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

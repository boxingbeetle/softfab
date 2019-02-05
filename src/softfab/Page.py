# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from collections import defaultdict
from typing import ClassVar, Type

from pageargs import PageArgs
from webgui import pageURL
from utils import SharedInstance, abstract

class Authenticator:
    '''Abstract base class of authentication wrappers.
    '''

    instance = SharedInstance() # type: ClassVar[SharedInstance]

    def authenticate(self, request):
        '''Authentication step: selects an authentication method depending on
        the page and the request.
        Returns a Deferred that has the user as a result, or LoginFailed
        or InternalError if authentication failed.
        '''
        raise NotImplementedError

    def askForAuthentication(self, req):
        '''Returns a Responder that asks the user to authenticate.
        Raises InternalError if there is something wrong with the
        authentication system.
        '''
        raise NotImplementedError

class AccessDenied(Exception):
    pass

class PresentableError(Exception):
    '''Raised if processing failed and there is a message describing the problem
    that can be presented to the user.
    The "message" field should contain an XML fragment to be inserted at the
    top level. UIPage will call presentError() with this message instead of
    calling presentContent().
    '''

class InvalidRequest(BaseException):
    '''Raised when the client request is found to be invalid.
    '''

class InternalError(BaseException):
    '''Raised when the Control Center encounters an internal problem or a
    configuration issue or invalid database state that cannot be corrected by
    the user.
    '''

class Redirect(BaseException):
    '''Can be raised to immediately end page generation and redirect to another
    page.
    '''
    def __init__(self, url):
        BaseException.__init__(self)
        self.url = url

class PageProcessor:
    '''Abstract base class for processors.
    '''
    error = None # page-specific error
    processingError = None # exception caught during processing
    page = None # set by parseAndProcess()

    def __init__(self, req):
        self.req = req
        self.__tables = {}

    def getTableData(self, table):
        return self.__tables[id(table)]

    def process(self, req):
        '''Process the given request for the page this processor belongs to.
        Typically this method returns nothing (implicit None).
        If processing uses an external service, a Deferred can be used to
        avoid blocking the reactor while waiting for the response. Note that
        the state of the Control Center can change between asynchronous calls;
        be careful not to use stale data.
        Raises Redirect to redirect the client to a different URL; the client
        is expected to fetch the new URL using HTTP GET.
        Raises AccessDenied if the user attempts an action for which he/she
        lacks the required privileges; the Control Center will display a
        generic error page using the message stored in the exception object.
        Raises ArgsCorrected if the page argument values are wrong or
        incomplete and can be automatically corrected; the Control Center will
        issue a redirect to the same page with the corrected argument values.
        Raises InvalidRequest if the request is invalid and should be reported
        to the client as such (HTTP status 400); the Control Center will
        present a generic error page using the message stored in the exception
        object.
        Raises PresentableError if the request is invalid but can be handled
        by the page (HTTP status 200); the Control Center will call the page's
        presentError() method with the message stored in the exception object.
        Raises InternalError if processing failed because of a server side
        problem (HTTP status 500); the Control Center will log the problem and
        display a generic error page.
        The default implementation of this method does nothing.
        '''

    def processTables(self):
        # While processing, perform a sanity check against multiple tables
        # using the same arguments.
        fields = defaultdict(set)
        args = self.args
        for table in self.page.iterDataTables(self):
            for propName in 'sortField', 'tabOffsetField':
                field = getattr(table, propName)
                if field is not None and args.isArgument(field):
                    used = fields[propName]
                    assert field not in used, propName
                    used.add(field)
            self.__tables[id(table)] = table.process(self)

    def subItemRelURL(self, subPath):
        '''Gets a relative URL to the given item subpath.
        '''
        return pageURL('%s/%s' % ( self.page.name, subPath ), self.args)

class Responder:
    '''Abstract base class for responders; responders are responsible for
    generating a response to an HTTP request.
    '''
    def respond(self, response, proc):
        '''Respond to a request using the given processing result.
        The output can either be written directly to the `response`
        object, or a delayed presenter can be returned as a Deferred
        or IProducer.
        '''
        raise NotImplementedError

class Redirector(PageProcessor, Responder):

    def __init__(self, req, url):
        PageProcessor.__init__(self, req)
        Responder.__init__(self)
        self.__url = url

    def respond(self, response, proc):
        assert proc is self
        response.sendRedirect(self.__url)

class HTTPAuthenticator(PageProcessor, Responder):

    def __init__(self, req, realm):
        PageProcessor.__init__(self, req)
        Responder.__init__(self)
        self.__realm = realm

    def respond(self, response, proc):
        assert proc is self
        response.setStatus(401)
        response.setHeader(
            'WWW-Authenticate', 'Basic realm="%s"' % self.__realm
            )

class FabResource(ABC):
    '''Abstract base class for Control Center pages.
    '''
    authenticationWrapper = abstract # type: ClassVar[Type[Authenticator]]
    streaming = False

    name = property(lambda self: self.getResourceName())

    @classmethod
    def getResourceName(cls):
        return cls.__name__.partition('_')[0]

    class Arguments(PageArgs):
        '''Every resource should declare its arguments in a class named
        'Arguments'.
        This default declaration does not contain any arguments.
        '''

    class Processor(PageProcessor):
        '''Every resource should have a Processor.
        This is a dummy one for resources that have no need for processing.
        '''

    def checkAccess(self, req):
        '''Check whether the user that made the given request is allowed to see
        this resource at all and raise AccessDenied if not.
        It is also possible to raise AccessDenied from the Processor if an
        acccess violation is detected at a later stage.
        '''
        raise NotImplementedError

    def getResponder(self, path, proc): # pylint: disable=unused-argument
        '''Returns a Responder that can present the given path within this
        resource. If the given path does not point to an item within this
        resource, KeyError is raised.
        The default implementation returns this resource itself when the path
        is None and raises KeyError otherwise.
        '''
        if path is None:
            return self
        else:
            raise KeyError('Resource does not contain subitems')

    def errorResponder(self, ex):
        '''Returns a Responder that can present an error page for the given
        exception.
        '''
        raise NotImplementedError

    def iterWidgets(self, proc): # pylint: disable=unused-argument
        '''Iterates through the widgets in the presentation of this resource.
        Currently only auto-updating widgets must be listed here, all other
        widgets are ignored for now.
        '''
        return iter(())

    def iterDataTables(self, proc): # pylint: disable=unused-argument
        '''Yields all DataTables on this resource.
        The default implementation yields no tables.
        '''
        yield from ()

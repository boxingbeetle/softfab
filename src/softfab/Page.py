# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from collections import defaultdict
from typing import (
    TYPE_CHECKING, Any, ClassVar, DefaultDict, Dict, Generic, Iterator,
    Optional, Set, Type, TypeVar, cast
)
import logging

from twisted.internet.defer import Deferred

from softfab.datawidgets import DataTable
from softfab.pageargs import ArgsT, PageArgs
from softfab.userlib import User
from softfab.utils import SharedInstance, abstract
from softfab.webgui import Widget, pageURL
from softfab.xmlgen import XML

if TYPE_CHECKING:
    from softfab.datawidgets import _TableData

def logPageException(req, message: str) -> None:
    """Logs an exception that occurred while handling a page request.
    """
    logging.exception(
        '%s:\n%s %s\n%s',
        message,
        req.method, req.getURL(),
        getattr(req, 'args', '(before or during argument parsing)')
        )

class Authenticator:
    '''Abstract base class of authenticators.
    '''

    instance = SharedInstance() # type: ClassVar[SharedInstance]

    def authenticate(self, req) -> Deferred:
        '''Authentication step: selects an authentication method depending on
        the page and the request.
        Returns a Deferred that has the user as a result, or LoginFailed
        or InternalError if authentication failed.
        '''
        raise NotImplementedError

    def askForAuthentication(self, req) -> 'Responder':
        '''Returns a Responder that asks the user to authenticate.
        Raises InternalError if there is something wrong with the
        authentication system.
        '''
        raise NotImplementedError

class PresentableError(Exception):
    '''Raised if processing failed and there is a message describing the problem
    that can be presented to the user.
    The "message" field should contain an XML fragment to be inserted at the
    top level. UIPage will call presentError() with this message instead of
    calling presentContent().
    '''

    def __init__(self, message: XML): # pylint: disable=useless-super-delegation
        # https://github.com/PyCQA/pylint/issues/2270
        super().__init__(message)

class InvalidRequest(Exception):
    '''Raised when the client request is found to be invalid.
    '''

class InternalError(Exception):
    '''Raised when the Control Center encounters an internal problem or a
    configuration issue or invalid database state that cannot be corrected by
    the user.
    '''

class Redirect(BaseException):
    '''Can be raised to immediately end page generation and redirect to another
    page.
    '''
    def __init__(self, url: str):
        BaseException.__init__(self)
        self.url = url

class PageProcessor(Generic[ArgsT]):
    """Abstract base class for processors.
    """

    error = None # type: Optional[XML]
    """Page-specific error."""

    processingError = None # type: Optional[Exception]
    """Exception caught during processing."""

    def __init__(self, req: Any):
        self.req = req
        self.__tables = {} # type: Dict[int, '_TableData']
        # set by parseAndProcess():
        self.args = cast(ArgsT, None)
        self.page = cast(FabResource[ArgsT, 'PageProcessor[ArgsT]'], None)

    def getTableData(self, table: DataTable) -> '_TableData':
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

    def processTables(self) -> None:
        # While processing, perform a sanity check against multiple tables
        # using the same arguments.
        fields = defaultdict(set) # type: DefaultDict[str, Set[str]]
        args = self.args
        for table in self.page.iterDataTables(self):
            for propName in 'sortField', 'tabOffsetField':
                field = getattr(table, propName)
                if field is not None and args.isArgument(field):
                    used = fields[propName]
                    assert field not in used, propName
                    used.add(field)
            self.__tables[id(table)] = table.process(self)

    def subItemRelURL(self, subPath: str) -> str:
        '''Gets a relative URL to the given item subpath.
        '''
        return pageURL('%s/%s' % ( self.page.name, subPath ), self.args)

ProcT = TypeVar('ProcT', bound=PageProcessor)

class Responder:
    '''Abstract base class for responders; responders are responsible for
    generating a response to an HTTP request.
    '''

    def respond(self, response):
        '''Respond to a request.
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

    def respond(self, response):
        response.sendRedirect(self.__url)

class HTTPAuthenticator(PageProcessor, Responder):

    def __init__(self, req, realm):
        PageProcessor.__init__(self, req)
        Responder.__init__(self)
        self.__realm = realm

    def respond(self, response):
        response.setStatus(401)
        response.setHeader(
            'WWW-Authenticate', 'Basic realm="%s"' % self.__realm
            )

class FabResource(ABC, Generic[ArgsT, ProcT]):
    '''Abstract base class for Control Center pages.
    '''
    authenticator = abstract # type: ClassVar[Type[Authenticator]]
    streaming = False

    debugSupport = False
    """Provide additional debug information as part of a reply?

    This could leak privileged information, so it should only be enabled
    in development environments.
    This flag can be enabled site-wide by using `softfab.TwistedApp.DebugRoot`
    as the root resource.
    """

    @property
    def name(self) -> str:
        return self.getResourceName()

    @classmethod
    def getResourceName(cls) -> str:
        return cls.__name__.partition('_')[0]

    class Arguments(PageArgs):
        '''Every resource should declare its arguments in a class named
        'Arguments'.
        This default declaration does not contain any arguments.
        '''

    class Processor(PageProcessor[ArgsT]):
        '''Every resource should have a Processor.
        This is a dummy one for resources that have no need for processing.
        '''

    def checkAccess(self, user: User) -> None:
        '''Check whether the given user is allowed to access this resource
        at all and raise AccessDenied if not.
        It is also possible to raise AccessDenied from the Processor if an
        acccess violation is detected at a later stage.
        '''
        raise NotImplementedError

    def getResponder(self, path: Optional[str], proc: ProcT) -> Responder:
        '''Returns a Responder that can present the given path within this
        resource. If the given path does not point to an item within this
        resource, KeyError is raised.
        The default implementation returns this resource itself when the path
        is None and raises KeyError otherwise.
        '''
        raise NotImplementedError

    def errorResponder(self, ex: Exception, proc: PageProcessor) -> Responder:
        '''Returns a Responder that can present an error page for the given
        exception.
        '''
        raise NotImplementedError

    def iterWidgets(self,
                    proc: ProcT # pylint: disable=unused-argument
                    ) -> Iterator[Widget]:
        '''Iterates through the widgets in the presentation of this resource.
        Currently only auto-updating widgets must be listed here, all other
        widgets are ignored for now.
        '''
        return iter(())

    def iterDataTables(self,
                       proc: ProcT # pylint: disable=unused-argument
                       ) -> Iterator[DataTable]:
        '''Yields all DataTables on this resource.
        The default implementation yields no tables.
        '''
        return iter(())

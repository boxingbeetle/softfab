# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from typing import (
    TYPE_CHECKING, Any, ClassVar, DefaultDict, Dict, Generic, Iterator,
    Optional, Set, TypeVar
)
import logging

from twisted.internet.defer import Deferred

from softfab.datawidgets import DataTable, TableData
from softfab.pageargs import ArgsT, PageArgs
from softfab.projectlib import Project
from softfab.response import Response
from softfab.userlib import User
from softfab.utils import abstract
from softfab.webgui import Widget, pageURL
from softfab.xmlgen import XML

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from softfab.request import Request
else:
    Request = Generic


def logPageException(req: Request, message: str) -> None:
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

    project: ClassVar[Project]

    def authenticate(self, req: Request) -> Deferred:
        '''Authentication step: selects an authentication method depending on
        the page and the request.
        Returns a Deferred that has the user as a result, or LoginFailed
        or InternalError if authentication failed.
        '''
        raise NotImplementedError

    def askForAuthentication(self,
                             req: Request,
                             message: Optional[str] = None
                             ) -> 'Responder':
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
        super().__init__()
        self.url = url

class PageProcessor(Generic[ArgsT]):
    """Abstract base class for processors.
    """

    project: ClassVar[Project]

    # Workaround for PyLint bug: https://github.com/PyCQA/pylint/issues/2981
    args: ArgsT

    error: Optional[XML] = None
    """Page-specific error."""

    processingError: Optional[Exception] = None
    """Exception caught during processing."""

    def __init__(self,
                 page: 'FabResource[ArgsT, PageProcessor[ArgsT]]',
                 req: Request[ArgsT],
                 args: ArgsT,
                 user: User
                 ):
        super().__init__()
        self.page = page
        self.req = req
        self.args = args
        self.user = user
        self.__tables: Dict[int, TableData] = {}

    def getTableData(self, table: DataTable) -> TableData:
        return self.__tables[id(table)]

    async def process(self, req: Request[ArgsT], user: User) -> None:
        '''Process the given request for the page this processor belongs to.
        If processing uses an external service, `await` can be used to
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
        fields: DefaultDict[str, Set[str]] = defaultdict(set)
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
        return pageURL(f'{self.page.name}/{subPath}', self.args)

ProcT = TypeVar('ProcT', bound=PageProcessor)

class Responder:
    '''Abstract base class for responders; responders are responsible for
    generating a response to an HTTP request.
    '''

    async def respond(self, response: Response) -> None:
        """Respond to a request by writing to the `response` object."""
        raise NotImplementedError

class Redirector(Responder):

    def __init__(self, url: str):
        super().__init__()
        self.__url = url

    async def respond(self, response: Response) -> None:
        response.sendRedirect(self.__url)

class HTTPAuthenticator(Responder):

    def __init__(self, realm: str, message: Optional[str] = None):
        super().__init__()
        self.__realm = realm
        self.__message = message

    async def respond(self, response: Response) -> None:
        response.setStatus(401, self.__message)
        response.setHeader('WWW-Authenticate', f'Basic realm="{self.__realm}"')

class FabResource(Generic[ArgsT, ProcT]):
    '''Abstract base class for Control Center pages.
    '''
    authenticator: Authenticator = abstract

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

    def errorResponder(self, ex: Exception, proc: ProcT) -> Responder:
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
                       ) -> Iterator[DataTable[Any]]:
        '''Yields all DataTables on this resource.
        The default implementation yields no tables.
        '''
        return iter(())

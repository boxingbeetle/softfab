# SPDX-License-Identifier: BSD-3-Clause

from cgi import parse_header
from inspect import signature
from typing import IO, Generic, Mapping, Optional, Tuple, Type, Union, cast
from urllib.parse import parse_qs, urljoin, urlparse

from twisted.web.server import Request as TwistedRequest, Session
from zope.interface import Attribute, Interface, implementer

from softfab.Page import InvalidRequest
from softfab.TwistedUtil import getRelativeRoot
from softfab.pageargs import ArgsT_co, Query
from softfab.useragent import UserAgent
from softfab.userlib import User
from softfab.users import Credentials
from softfab.utils import cachedProperty
import softfab.config

# The 'sameSite' parameter was added in Twisted 18.9.0.
sameSiteSupport = 'sameSite' in signature(TwistedRequest.addCookie).parameters

class RequestBase:
    '''Contains the request information that is available during all request
    handling steps.
    '''

    def __init__(self, request: TwistedRequest):
        super().__init__()
        self._request = request

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self._request!r})'

    @cachedProperty
    def userAgent(self) -> UserAgent:
        getHeader = self._request.getHeader
        return UserAgent(getHeader('user-agent'), getHeader('accept'))

    @cachedProperty
    def referer(self) -> Optional[str]:
        '''The Control Center page plus query that the user visited
        before the current page, or None if not applicable.
        '''
        url = self._request.getHeader('referer')
        return None if url is None else self.relativeURL(url)

    @cachedProperty
    def refererPage(self) -> Optional[str]:
        '''The Control Center page without query that the user visited
        before the current page, or None if not applicable.
        '''
        referer = self.referer
        if referer is None:
            return None
        return urlparse(referer).path

    @cachedProperty
    def refererQuery(self) -> Optional[Query]:
        '''The query of the Control Center page that the user visited
        before the current page, or None if not applicable.
        '''
        referer = self.referer
        if referer is None:
            return None
        query = urlparse(referer).query
        return Query(parse_qs(query, keep_blank_values=True))

    @cachedProperty
    def contentType(self) -> Union[Tuple[str, Mapping[str, str]],
                                   Tuple[None, None]]:
        '''A pair of the media type and a dictionary of parameters
        that describes the body of this request, or (None, None)
        if the request did not contain a Content-Type header.
        Both the media type and parameter names will be in lower case,
        while parameter values will be as provided by the client.
        '''
        header = self._request.getHeader('content-type')
        if header is None:
            return None, None
        else:
            # cgi.parse_header() will convert parameter names to lower
            # case, but not media type. Media type is case insensitive:
            #   https://tools.ietf.org/html/rfc7231#section-3.1.1.1
            mediaType, params = parse_header(header)
            return mediaType.lower(), params

    # Generic request methods:

    def rawInput(self) -> IO[bytes]:
        return self._request.content

    @property
    def displayTracebacks(self) -> bool:
        """True iff tracebacks should be shown on errors.
        This is useful for debugging, but might expose sensitive information,
        so it shouldn't be done for production sites.
        """
        return self._request.site.displayTracebacks

    @cachedProperty
    def method(self) -> str:
        return self._request.method.decode()

    def getURL(self) -> str:
        url = self._request.uri.decode()
        if url.startswith('/'):
            # Make URL relative so it will work behind a reverse proxy.
            return url[1 : ]
        else:
            return url

    def getSubPath(self) -> Optional[str]:
        '''If an item inside a page was requested, returns the path of that
        item in the page. If the page itself was requested None is returned.
        '''
        request = self._request
        path = request.path
        pagePath = b'/'.join([ b'' ] + request.prepath)
        if path == pagePath:
            return None
        assert path.startswith(pagePath + b'/')
        return path[len(pagePath) + 1 : ].decode()

    @property
    def relativeRoot(self) -> str:
        """Relative URL from the requested page to the site root.
        Ends in a slash when non-empty.
        """
        return getRelativeRoot(self._request)

    def relativeURL(self, url: str) -> Optional[str]:
        """Return a path relative to this site's root that corresponds to
        the given full URL or URL path, or None if the given URL doesn't
        belong to this site or it points to the Login page.
        """
        rootURL = softfab.config.rootURL
        absolute = urljoin(rootURL, url)
        if not absolute.startswith(rootURL):
            # URL belongs to a different site.
            return None
        relative = absolute[len(rootURL) : ]
        page = urlparse(relative).path
        if page == 'Login':
            # The Login page was the previously requested page, but it is not
            # the actual referer (that information is lost).
            return None
        return relative

class Request(RequestBase, Generic[ArgsT_co]):
    '''Contains the request information that is only available during the
    "parse" and "process" request handling steps.
    '''

    def __init__(self, request: TwistedRequest):
        super().__init__(request)
        self.args = cast(ArgsT_co, None)

    def processEnd(self) -> None:
        '''Called when the processing step is done.
        Reduces the interface of the request object.
        '''
        self.__class__ = RequestBase # type: ignore[assignment]

    def parseArgs(self, argsClass: Type[ArgsT_co]) -> ArgsT_co:
        '''Initialises the Arguments, if the page has one.
        '''
        # Decode field names.
        # Values are decoded when a field is claimed by a page argument.
        fields = {}
        for keyBytes, values in self._request.args.items():
            if not keyBytes:
                # Konqueror 3.5.2 submits nameless controls with an empty name,
                # instead of omitting them from the submission.
                # This happens on the predefined tags dropdown boxes from
                # selectview.tagValueEditTable().
                continue
            try:
                key = keyBytes.decode('ascii')
            except UnicodeDecodeError as ex:
                raise InvalidRequest(
                    f'Error decoding argument name {keyBytes!r}: {ex}'
                    ) from ex
            fields[key] = values

        return argsClass.parse(fields, self)

    # For HTTP basic auth:

    def getCredentials(self) -> Credentials:
        """Returns the name and password provided as part of this request.
        If no name and/or password was provided, that string will be empty.
        @raise UnicodeDecodeError: If the strings are not valid UTF-8.
        """
        request = self._request
        # Twisted < 20.3.0 will return an empty 'str' instead of 'bytes'
        # when the user or password is missing.
        #   https://twistedmatrix.com/trac/ticket/9596
        userName: Union[bytes, str] = request.getUser()
        if isinstance(userName, bytes):
            userName = userName.decode()
        password: Union[bytes, str] = request.getPassword()
        if isinstance(password, bytes):
            password = password.decode()
        return Credentials(userName, password)

    # Session management:

    sessionCookieName = b'SF_CC_SESSION'

    def _getSession(self) -> Optional[Session]:
        '''Returns the active session on the given Twisted request object,
        or None if there is no active session.
        '''
        request = self._request
        sessionID = request.getCookie(self.sessionCookieName)
        if sessionID is None:
            return None
        try:
            return request.site.getSession(sessionID)
        except KeyError:
            return None

    def startSession(self, user: User) -> None:
        '''Starts a new session and returns it.
        '''
        request = self._request
        site = request.site
        session = site.makeSession()
        session.setComponent(ISessionData, SessionData(user))
        session.touch()
        request.addCookie(
            self.sessionCookieName, session.uid, path='/',
            httpOnly=True, secure=site.secureCookie,
            **({'sameSite': 'lax'} if sameSiteSupport else {})
            )

    def stopSession(self) -> bool:
        '''Expires the current session, if any.
        Returns True iff there was an active session.
        '''
        session = self._getSession()
        if session is None:
            return False
        else:
            session.expire()
            return True

    def loggedInUser(self) -> Optional[User]:
        """Gets the logged-in user (if any) making this request.
        Also resets the session timeout.
        """
        session = self._getSession()
        if session is not None:
            sessionData = session.getComponent(ISessionData)
            if sessionData is not None:
                user = sessionData.user
                if user.isActive():
                    session.touch()
                    return user
        return None

class ISessionData(Interface): # pylint: disable=inherit-non-class
    """State kept as part of a session.
    """

    user = Attribute("""User""")

@implementer(ISessionData)
class SessionData:

    def __init__(self, user: User):
        super().__init__()
        self.user = user

# SPDX-License-Identifier: BSD-3-Clause

from cgi import parse_header
from inspect import signature
from typing import IO, Generic, Mapping, Optional, Sequence, Tuple, Type, cast
from urllib.parse import parse_qs, urlparse

from twisted.web.http import Request as TwistedRequest
from twisted.web.server import Session
from zope.interface import Attribute, Interface, implementer

from softfab.Page import InvalidRequest
from softfab.config import rootURL
from softfab.pageargs import ArgsT
from softfab.projectlib import project
from softfab.useragent import UserAgent
from softfab.userlib import User
from softfab.utils import cachedProperty

# The 'sameSite' parameter was added in Twisted 18.9.0.
sameSiteSupport = 'sameSite' in signature(TwistedRequest.addCookie).parameters

class LongSession(Session):
    sessionTimeout = 60 * 60 * 24 * 7 # one week in seconds

class RequestBase:
    '''Contains the request information that is available during all request
    handling steps.
    '''

    def __init__(self, request: TwistedRequest, user: User):
        self._request = request
        self._user = user

    def __repr__(self) -> str:
        return '%s(%r, %r)' % (
            self.__class__.__name__, self._request, self._user
            )

    @cachedProperty
    def userAgent(self) -> UserAgent:
        getHeader = self._request.getHeader
        return UserAgent(getHeader('user-agent'), getHeader('accept'))

    @cachedProperty
    def referer(self) -> Optional[str]:
        '''The Control Center page plus query that the user visited
        before the current page, or None if not applicable.
        '''
        refererURL = self._request.getHeader('referer')
        if refererURL is None:
            # No referer header.
            return None
        if not refererURL.startswith(rootURL):
            # Referer is a different site.
            return None
        referer = refererURL[len(rootURL) : ]
        page = urlparse(referer).path
        if page == 'Login':
            # The Login page was the previously requested page, but it is not
            # the actual referer (that information is lost).
            return None
        return referer

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
    def refererQuery(self) -> Optional[Sequence[Tuple[str, Sequence[str]]]]:
        '''The query of the Control Center page that the user visited
        before the current page, or None if not applicable.
        '''
        referer = self.referer
        if referer is None:
            return None
        query = urlparse(referer).query
        return tuple(
            (key, tuple(value))
            for key, value in parse_qs(query, keep_blank_values=True).items()
            )

    @cachedProperty
    def contentType(self) -> Tuple[Optional[str], Optional[Mapping[str, str]]]:
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
    def secure(self) -> bool:
        return self._request.isSecure()

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

    # User information:

    @property
    def user(self) -> User:
        """The user who made this request.
        """
        return self._user

class Request(RequestBase, Generic[ArgsT]):
    '''Contains the request information that is only available during the
    "parse" and "process" request handling steps.
    '''

    def __init__(self, request: TwistedRequest, user: User):
        super().__init__(request, user)
        self.args = cast(ArgsT, None)

    def processEnd(self) -> None:
        '''Called when the processing step is done.
        Reduces the interface of the request object.
        '''
        self.__class__ = RequestBase # type: ignore

    def parseArgs(self, argsClass: Type[ArgsT]) -> ArgsT:
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
                    'Error decoding argument name %r: %s' % (keyBytes, ex)
                    )
            fields[key] = values

        return argsClass.parse(fields, self)

    # For HTTP basic auth:

    def getCredentials(self) -> Tuple[str, str]:
        """Returns the name and password provided as part of this request.
        If no name and/or password was provided, the string will be empty.
        Raises UnicodeDecodeError if the strings are not valid UTF-8.
        """
        request = self._request
        # Twisted will return an empty 'str' instead of 'bytes' when the
        # user or password is missing.
        #   https://twistedmatrix.com/trac/ticket/9596
        userName = request.getUser()
        if isinstance(userName, bytes):
            userName = userName.decode()
        password = request.getPassword()
        if isinstance(password, bytes):
            password = password.decode()
        return userName, password

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

    def startSession(self, user: User, secure: bool) -> None:
        '''Starts a new session and returns it.
        '''
        request = self._request
        site = request.site
        site.sessionFactory = LongSession
        session = site.makeSession()
        session.setComponent(ISessionData, SessionData(user))
        session.touch()
        request.addCookie(
            self.sessionCookieName, session.uid, path='/',
            httpOnly=True, secure=secure,
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
            self._user = project.defaultUser
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

    def __init__(self, user):
        self.user = user

# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import AccessDenied, InvalidRequest, Redirect
from softfab.config import rootURL
from softfab.useragent import UserAgent
from softfab.userlib import privileges
from softfab.utils import cachedProperty, iterable

from cgi import parse_header
from urllib.parse import parse_qs, urlparse

class RequestBase:
    '''Contains the request information that is available during all request
    handling steps.
    '''

    def __init__(self, request, user):
        self._request = request
        self._user = user

    def __repr__(self):
        return '%s(%r, %r)' % (
            self.__class__.__name__, self._request, self._user
            )

    @cachedProperty
    def userAgent(self):
        getHeader = self._request.getHeader
        return UserAgent(getHeader('user-agent'), getHeader('accept'))

    @cachedProperty
    def referer(self):
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
    def refererPage(self):
        '''The Control Center page without query that the user visited
        before the current page, or None if not applicable.
        '''
        referer = self.referer
        if referer is None:
            return None
        return urlparse(referer).path

    @cachedProperty
    def refererQuery(self):
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
    def contentType(self):
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

    def rawInput(self):
        return self._request.content

    @cachedProperty
    def method(self):
        return self._request.method.decode()

    def getURL(self):
        url = self._request.uri.decode()
        if url.startswith('/'):
            # Make URL relative so it will work behind a reverse proxy.
            return url[1 : ]
        else:
            return url

    def getSubPath(self):
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

    def getUser(self):
        '''Returns an object that implements IUser and describes the user who
        made this request.
        '''
        return self._user

    def getUserName(self):
        '''Returns the name of the user who made this request.
        If this request does not (yet) have an authenticated user associated
        with it, None is returned.
        '''
        return self._user.getUserName()

class Request(RequestBase):
    '''Contains the request information that is only available during the
    "parse" and "process" request handling steps.
    '''

    def processEnd(self):
        '''Called when the processing step is done.
        Reduces the interface of the request object.
        '''
        self.__class__ = RequestBase

    def _parse(self, page):
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

        self.args = page.Arguments.parse(fields, self) # pylint: disable=attribute-defined-outside-init

    def checkDirect(self):
        '''If request is made through our proxy, redirect directly to Twisted's
        HTTP server. This avoids Apache's mod_proxy buffering the reply, which
        causes big delays in reception of streamed data.
        A cleaner solution would be to use the HTTP 1.1 chunked transfer
        encoding, but twisted.web does not support that yet (web2 does, but is
        being phased out). Also we would have to check that all clients
        understand HTTP 1.1 (or keep this workaround for HTTP 1.0 clients).
        '''
        hostIP = self._request.host
        directHost = '%s:%d' % ( hostIP.host, hostIP.port )
        if self._request.getHeader('host') != directHost:
            raise Redirect('http://%s%s' % ( directHost, self._request.uri ))

    # Session management:

    sessionCookieName = b'SF_CC_SESSION'

    @classmethod
    def getSession(cls, request):
        '''Returns the active session on the given Twisted request object,
        or None if there is no active session.
        '''
        sessionID = request.getCookie(cls.sessionCookieName)
        if sessionID is None:
            return None
        try:
            return request.site.getSession(sessionID)
        except KeyError:
            return None

    def startSession(self):
        '''Starts a new session and returns it.
        '''
        request = self._request
        session = request.site.makeSession()
        session.touch()
        request.addCookie(self.sessionCookieName, session.uid, path = '/')
        return session

    def stopSession(self):
        '''Expires the current session, if any.
        Returns True iff there was an active session.
        '''
        session = self.getSession(self._request)
        if session is None:
            return False
        else:
            session.expire()
            return True

    # Privilege checks:

    def hasPrivilege(self, priv):
        return self._user.hasPrivilege(priv)

    def checkPrivilege(self, priv, text = None):
        if not self.hasPrivilege(priv):
            if text is None:
                raise AccessDenied()
            else:
                raise AccessDenied(text)

    def checkPrivilegeForOwned(self, priv, records, text = ''):
        '''Checks whether the current user is allowed to perform an action
        on an owned database record.
        @param records Record or sequence of records to test for ownership.
        @param text String to display if the user is not allowed to perform
          the action, or a tuple of which the first element is the string to
          display if the user is not allowed to perform the action on this
          particular record and the second element is the string to display
          if the user is not allowed to perform the action on any record
          of this type.
        '''
        assert not priv.endswith('o'), priv
        if self.hasPrivilege(priv):
            # User is allowed to take action also for non-owned records.
            return
        ownedPriv = priv + 'o'
        hasOwnedPriv = ownedPriv in privileges and self.hasPrivilege(ownedPriv)
        if hasOwnedPriv:
            # User is allowed to perform action, but only for owned records.
            userName = self._user.getUserName()
            if not iterable(records):
                records = ( records, )
            if all(record.getOwner() == userName for record in records):
                return
        # Construct error message.
        if isinstance(text, tuple):
            text = text[0 if hasOwnedPriv else 1]
        if text is None:
            raise AccessDenied()
        else:
            raise AccessDenied(text)

# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import (
    Authenticator, HTTPAuthenticator, InternalError, Redirector
    )
from softfab.request import Request
from softfab.userlib import IUser, SuperUser, UnknownUser, authenticate
from softfab.utils import encodeURL

from twisted.cred.error import LoginFailed
from twisted.internet import defer

from typing import Optional

def loggedInUser(request) -> Optional[IUser]:
    """Gets the logged-in user making the request.
    Also resets the session timeout.
    """
    session = Request.getSession(request)
    if session is not None:
        user = session.getComponent(IUser)
        if user is not None and user.isActive():
            session.touch()
            return user
    return None

class LoginAuthPage(Authenticator):
    '''Page wrapper that performs authentication using a login page and
    a session cookie.
    '''

    def authenticate(self, request):
        user = loggedInUser(request)
        if user is None:
            # User must log in.
            return defer.fail(LoginFailed())
        else:
            # User has already authenticated.
            return defer.succeed(user)

    def askForAuthentication(self, req):
        return Redirector(
            req, 'Login?%s' % encodeURL(( ('url', req.getURL()), ))
            )

class HTTPAuthPage(Authenticator):
    '''Page wrapper that performs HTTP authentication.
    '''

    def authenticate(self, request):
        # To avoid cross-site request forgery, we must authenticate every API
        # call and not use session cookies. Since API calls are not made using
        # web browsers, most likely the client is not using session cookies
        # anyway.
        #   http://en.wikipedia.org/wiki/Cross-site_request_forgery
        userNameBytes = request.getUser()
        if userNameBytes:
            # If requester supplied user name, authenticate as that user.
            try:
                userName = userNameBytes.decode()
                password = request.getPassword().decode()
            except UnicodeDecodeError as ex:
                return defer.fail(LoginFailed(ex))
            return authenticate(userName, password)

        # No user name supplied.
        return defer.fail(LoginFailed())

    def askForAuthentication(self, req):
        return HTTPAuthenticator(req, 'SoftFab')

class NoAuthPage(Authenticator):
    '''Page wrapper that performs no authentication and returns
    a non-privileged user.
    '''

    def authenticate(self, request):
        return defer.succeed(UnknownUser())

    def askForAuthentication(self, req):
        raise InternalError(
            'Authentication requested for page that does not require it.'
            )

class DisabledAuthPage(Authenticator):
    '''Page wrapper that forces no authentication and returns
    a user with all privileges when not logged in.
    This is for ease of development, not recommended for production.
    '''

    def authenticate(self, request):
        user = loggedInUser(request)
        if user is None:
            return defer.succeed(SuperUser())
        else:
            # Use logged-in user.
            return defer.succeed(user)

    def askForAuthentication(self, req):
        raise InternalError(
            'Authentication requested while authentication is disabled.'
            )

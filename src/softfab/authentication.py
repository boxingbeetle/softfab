# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import (
    Authenticator, HTTPAuthenticator, InternalError, Redirector
    )
from softfab.config import enableSecurity
from softfab.request import Request
from softfab.userlib import IUser, SuperUser, UnknownUser, authenticate
from softfab.utils import encodeURL

from twisted.cred.error import LoginFailed
from twisted.internet import defer

class LoginAuthPage(Authenticator):
    '''Page wrapper that performs authentication using a login page and
    a session cookie.
    '''

    def authenticate(self, request):
        if not enableSecurity:
            # Authorization is disabled: user is allowed to do anything.
            return defer.succeed(SuperUser())

        # Check for active session.
        session = Request.getSession(request)
        if session is not None:
            user = session.getComponent(IUser)
            if user is not None and user.isActive():
                # User has already authenticated.
                session.touch()
                return defer.succeed(user)

        # No active session; user must log in.
        return defer.fail(LoginFailed())

    def askForAuthentication(self, req):
        return Redirector(
            req, 'Login?%s' % encodeURL(( ('url', req.getURL()), ))
            )

class HTTPAuthPage(Authenticator):
    '''Page wrapper that performs HTTP authentication.
    '''

    def authenticate(self, request):
        if not enableSecurity:
            # Authorization is disabled: user is allowed to do anything.
            return defer.succeed(SuperUser())

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
    '''Page wrapper that performs no authentication.
    '''

    def authenticate(self, request):
        # No authentication: run as a user with no privileges.
        return defer.succeed(UnknownUser())

    def askForAuthentication(self, req):
        raise InternalError(
            'Authentication requested for page that does not require it.'
            )

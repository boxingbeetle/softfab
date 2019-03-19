# SPDX-License-Identifier: BSD-3-Clause

from twisted.cred.error import LoginFailed
from twisted.internet.defer import Deferred, fail, succeed
from twisted.web.http import Request as TwistedRequest

from softfab.Page import (
    Authenticator, HTTPAuthenticator, InternalError, Redirector, Responder
)
from softfab.pagelinks import loginURL
from softfab.projectlib import project
from softfab.request import Request
from softfab.userlib import AnonGuestUser, SuperUser, UnknownUser, authenticate


class LoginAuthPage(Authenticator):
    '''Authenticator that performs authentication using a login page and
    a session cookie.
    '''

    def authenticate(self, request: TwistedRequest) -> Deferred:
        user = Request.loggedInUser(request)
        if user is None:
            if project['anonguest']:
                return succeed(AnonGuestUser())
            else:
                # User must log in.
                return fail(LoginFailed())
        else:
            # User has already authenticated.
            return succeed(user)

    def askForAuthentication(self, req: Request) -> Responder:
        return Redirector(req, loginURL(req))

class HTTPAuthPage(Authenticator):
    '''Authenticator that performs HTTP authentication.
    '''

    def authenticate(self, request: TwistedRequest) -> Deferred:
        # To avoid cross-site request forgery, we must authenticate every API
        # call and not use session cookies. Since API calls are not made using
        # web browsers, most likely the client is not using session cookies
        # anyway.
        #   http://en.wikipedia.org/wiki/Cross-site_request_forgery
        userNameBytes = request.getUser() # type: bytes
        if userNameBytes:
            # If requester supplied user name, authenticate as that user.
            try:
                userName = userNameBytes.decode()
                password = request.getPassword().decode()
            except UnicodeDecodeError as ex:
                return fail(LoginFailed(ex))
            return authenticate(userName, password)

        # No user name supplied.
        if project['anonguest']:
            return succeed(AnonGuestUser())
        else:
            return fail(LoginFailed())

    def askForAuthentication(self, req: Request) -> Responder:
        return HTTPAuthenticator(req, 'SoftFab')

class NoAuthPage(Authenticator):
    '''Authenticator that performs no authentication and returns
    a non-privileged user.
    '''

    def authenticate(self, request: TwistedRequest) -> Deferred:
        return succeed(UnknownUser())

    def askForAuthentication(self, req: Request) -> Responder:
        raise InternalError(
            'Authentication requested for page that does not require it.'
            )

class DisabledAuthPage(Authenticator):
    '''Authenticator that forces no authentication and returns
    a user with all privileges when not logged in.
    This is for ease of development, not recommended for production.
    '''

    def authenticate(self, request: TwistedRequest) -> Deferred:
        user = Request.loggedInUser(request)
        if user is None:
            return succeed(SuperUser())
        else:
            # Use logged-in user.
            return succeed(user)

    def askForAuthentication(self, req: Request) -> Responder:
        raise InternalError(
            'Authentication requested while authentication is disabled.'
            )

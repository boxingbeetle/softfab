# SPDX-License-Identifier: BSD-3-Clause

from twisted.cred.error import LoginFailed
from twisted.internet.defer import Deferred, fail, succeed

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

    def authenticate(self, req: Request) -> Deferred:
        user = req.loggedInUser()
        if user is not None:
            # User has already authenticated.
            return succeed(user)
        elif project['anonguest']:
            return succeed(AnonGuestUser())
        else:
            # User must log in.
            return fail(LoginFailed())

    def askForAuthentication(self, req: Request) -> Responder:
        return Redirector(loginURL(req))

class HTTPAuthPage(Authenticator):
    '''Authenticator that performs HTTP authentication.
    '''

    def authenticate(self, req: Request) -> Deferred:
        # To avoid cross-site request forgery, we must authenticate every API
        # call and not use session cookies. Since API calls are not made using
        # web browsers, most likely the client is not using session cookies
        # anyway.
        #   http://en.wikipedia.org/wiki/Cross-site_request_forgery
        try:
            userName, password = req.getCredentials()
        except UnicodeDecodeError as ex:
            return fail(LoginFailed(ex))

        if userName:
            return authenticate(userName, password)
        elif project['anonguest']:
            return succeed(AnonGuestUser())
        else:
            return fail(LoginFailed())

    def askForAuthentication(self, req: Request) -> Responder:
        return HTTPAuthenticator(req, 'SoftFab')

class NoAuthPage(Authenticator):
    '''Authenticator that performs no authentication and returns
    a non-privileged user.
    '''

    def authenticate(self, req: Request) -> Deferred:
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

    def authenticate(self, req: Request) -> Deferred:
        user = req.loggedInUser()
        if user is None:
            return succeed(SuperUser())
        else:
            # Use logged-in user.
            return succeed(user)

    def askForAuthentication(self, req: Request) -> Responder:
        raise InternalError(
            'Authentication requested while authentication is disabled.'
            )

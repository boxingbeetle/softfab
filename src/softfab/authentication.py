# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Optional

from twisted.cred.error import LoginFailed, Unauthorized
from twisted.internet.defer import Deferred, fail, succeed

from softfab.Page import (
    Authenticator, HTTPAuthenticator, InternalError, Redirector, Responder
)
from softfab.pagelinks import loginURL
from softfab.projectlib import project
from softfab.request import Request
from softfab.tokens import TokenRole, TokenUser, authenticateToken
from softfab.userlib import (
    AnonGuestUser, SuperUser, UnknownUser, authenticateUser
)
from softfab.utils import SharedInstance


class LoginAuthPage(Authenticator):
    '''Authenticator that performs authentication using a login page and
    a session cookie.
    '''

    instance = SharedInstance() # type: ClassVar[SharedInstance]

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

    def askForAuthentication(self,
                             req: Request,
                             message: Optional[str] = None
                             ) -> Responder:
        return Redirector(loginURL(req))

class HTTPAuthPage(Authenticator):
    '''Authenticator that performs HTTP authentication.
    '''

    instance = SharedInstance() # type: ClassVar[SharedInstance]

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
            return authenticateUser(userName, password)
        elif project['anonguest']:
            return succeed(AnonGuestUser())
        else:
            return fail(LoginFailed())

    def askForAuthentication(self,
                             req: Request,
                             message: Optional[str] = None
                             ) -> Responder:
        return HTTPAuthenticator('SoftFab', message)

class TokenAuthPage(Authenticator):
    '''Authenticator that performs HTTP authentication using an access token.
    '''

    def __init__(self, role: TokenRole):
        self.__role = role

    def authenticate(self, req: Request) -> Deferred:
        try:
            tokenId, password = req.getCredentials()
        except UnicodeDecodeError as ex:
            return fail(LoginFailed(ex))

        if tokenId:
            try:
                token = authenticateToken(tokenId, password)
            except KeyError:
                return fail(LoginFailed(
                    'Token "%s" does not exist' % tokenId
                    ))
            if token.role is not self.__role:
                return fail(Unauthorized(
                    'Token "%s" is of the wrong type for this operation'
                    % tokenId
                    ))
            return succeed(TokenUser(token))
        elif project['anonguest']:
            return succeed(AnonGuestUser())
        else:
            return fail(LoginFailed())

    def askForAuthentication(self,
                             req: Request,
                             message: Optional[str] = None
                             ) -> Responder:
        return HTTPAuthenticator('SoftFab', message)

class NoAuthPage(Authenticator):
    '''Authenticator that performs no authentication and returns
    a non-privileged user.
    '''

    instance = SharedInstance() # type: ClassVar[SharedInstance]

    def authenticate(self, req: Request) -> Deferred:
        return succeed(UnknownUser())

    def askForAuthentication(self,
                             req: Request,
                             message: Optional[str] = None
                             ) -> Responder:
        raise InternalError(
            'Authentication requested for page that does not require it.'
            )

class DisabledAuthPage(Authenticator):
    '''Authenticator that forces no authentication and returns
    a user with all privileges when not logged in.
    This is for ease of development, not recommended for production.
    '''

    instance = SharedInstance() # type: ClassVar[SharedInstance]

    def authenticate(self, req: Request) -> Deferred:
        user = req.loggedInUser()
        if user is None:
            return succeed(SuperUser())
        else:
            # Use logged-in user.
            return succeed(user)

    def askForAuthentication(self,
                             req: Request,
                             message: Optional[str] = None
                             ) -> Responder:
        raise InternalError(
            'Authentication requested while authentication is disabled.'
            )

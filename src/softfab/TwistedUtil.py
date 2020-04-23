# SPDX-License-Identifier: BSD-3-Clause

from typing import cast

from twisted.web.http import Request as TwistedRequest
from twisted.web.iweb import IRequest
from twisted.web.resource import IResource, Resource
from twisted.web.util import redirectTo
from zope.interface import implementer

from softfab.compat import NoReturn
from softfab.userlib import AccessDenied


def getRelativeRoot(request: IRequest) -> str:
    """Relative URL from the requested page to the site root.
    Ends in a slash when non-empty.
    """
    return '../' * (len(request.prepath) - 1)

class PageRedirect(Resource):
    '''Redirect to a fixed page.
    '''
    isLeaf = True

    def __init__(self, page: str):
        super().__init__()
        self.page = page

    def render(self, request: IRequest) -> bytes:
        return redirectTo(self.page.encode(), request)

    def getChild(self, path: str, request: IRequest) -> Resource:
        return self

@implementer(IResource)
class ClientErrorResource:
    isLeaf = True
    code = 400

    # PyLint doesn't understand Zope interfaces.
    # pylint: disable=unused-argument

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def getChildWithDefault(self,
                            name: bytes,
                            request: TwistedRequest
                            ) -> NoReturn:
        # Will not be called because isLeaf is true.
        assert False

    def putChild(self,
                 path: bytes,
                 child: IResource
                 ) -> NoReturn:
        # Error resources don't support children.
        assert False

    def render(self, request: TwistedRequest) -> bytes:
        request.setResponseCode(self.code)
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
        return self.message.encode() + b'\n'

class UnauthorizedResource(ClientErrorResource):
    code = 401

    def __init__(self, realm: str, message: str):
        super().__init__(message)
        self.realm = realm

    def render(self, request: TwistedRequest) -> bytes:
        body = super().render(request)
        request.setHeader(
            b'WWW-Authenticate',
            b'Basic realm="%s"' % self.realm.encode('ascii')
            )
        return body

class AccessDeniedResource(ClientErrorResource):
    code = 403

    @classmethod
    def fromException(cls, ex: AccessDenied) -> 'AccessDeniedResource':
        message = 'Access denied'
        if ex.args:
            message += ': ' + cast(str, ex.args[0])
        return cls(message)

class NotFoundResource(ClientErrorResource):
    code = 404

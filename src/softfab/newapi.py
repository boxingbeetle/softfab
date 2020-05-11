# SPDX-License-Identifier: BSD-3-Clause

"""Temporary module that contains a more RESTful API.
This should become the public API at some point, but for now it is
only used as an internal API by the command line interface.
"""

from os.path import splitext
from typing import Mapping
from urllib.parse import unquote_plus
import json

from twisted.web.http import Request
from twisted.web.resource import Resource
import attr

from softfab.TwistedUtil import ClientErrorResource, NotFoundResource
from softfab.roles import UIRoleNames
from softfab.userlib import UserInfo, userDB


def textReply(request: Request, status: int, message: str) -> bytes:
    """Replies to an HTTP request with a plain text message.
    The reply body is returned.
    """
    request.setResponseCode(status)
    request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
    return message.encode()

@attr.s(auto_attribs=True)
class UserData:
    name: str
    role: UIRoleNames

    @classmethod
    def fromUserInfo(cls, user: UserInfo) -> 'UserData':
        return cls(user.name, user.uiRole)

def dataToJSON(data: UserData) -> Mapping[str, str]:
    return {
        'name': data.name,
        'role': data.role.name.lower()
        }

class UserResource(Resource):
    """HTTP resource for an existing user account."""

    def __init__(self, user: UserData):
        super().__init__()
        self._user = user

    def getChildWithDefault(self, path: bytes, request: Request) -> Resource:
        return NotFoundResource('Records do not support subpaths')

    def render_GET(self, request: Request) -> bytes:
        request.setHeader(b'Content-Type', b'application/json; charset=UTF-8')
        return json.dumps(dataToJSON(self._user)).encode()

class NoUserResource(Resource):
    """HTTP resource for a non-existing user account."""

    def __init__(self, name: str):
        super().__init__()
        self._name = name

    def getChildWithDefault(self, path: bytes, request: Request) -> Resource:
        return NotFoundResource('Records do not support subpaths')

    def render_GET(self, request: Request) -> bytes:
        return textReply(request, 404, f"User not found: {self._name}\n")

class UsersResource(Resource):

    def getChildWithDefault(self, path: bytes, request: Request) -> Resource:
        if not path:
            return self

        try:
            segment = unquote_plus(path.decode(), errors='strict')
        except UnicodeError:
            return ClientErrorResource('Path is not valid')

        name, ext = splitext(segment)
        if not ext:
            return NotFoundResource('Missing file name extension')
        if ext != '.json':
            return NotFoundResource('Currently only ".json" is supported')

        try:
            user = userDB[name]
        except KeyError:
            return NoUserResource(name)
        else:
            return UserResource(UserData.fromUserInfo(user))

    def render_GET(self, request: Request) -> bytes:
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
        return b'User index not implemented yet\n'

def createAPIRoot() -> Resource:
    root = Resource()
    root.putChild(b'users', UsersResource())
    return root

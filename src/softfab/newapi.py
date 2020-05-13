# SPDX-License-Identifier: BSD-3-Clause

"""Temporary module that contains a more RESTful API.
This should become the public API at some point, but for now it is
only used as an internal API by the command line interface.
"""

from enum import Enum, auto
from os.path import splitext
from urllib.parse import unquote_plus
import json

from twisted.web.http import Request
from twisted.web.resource import Resource
import attr

from softfab.TwistedUtil import ClientErrorResource, NotFoundResource
from softfab.json import dataToJSON, jsonToData
from softfab.roles import UIRoleNames, uiRoleToSet
from softfab.userlib import UserInfo, addUserAccount, removeUserAccount, userDB


class DataFormat(Enum):
    """The data format to use for presenting a resource."""
    AUTO = auto()
    JSON = auto()

def textReply(request: Request, status: int, message: str) -> bytes:
    """Replies to an HTTP request with a plain text message.
    The reply body is returned.
    """
    request.setResponseCode(status)
    request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
    return message.encode()

@attr.s(auto_attribs=True)
class UserData:
    # TODO: Name is redundant on PUT; accept a default of None?
    name: str
    role: UIRoleNames

    @classmethod
    def fromUserInfo(cls, user: UserInfo) -> 'UserData':
        return cls(user.name, user.uiRole)

class UserResource(Resource):
    """HTTP resource for an existing user account."""

    def __init__(self, user: UserData, fmt: DataFormat):
        super().__init__()
        self._user = user
        self._format = fmt

    def getChildWithDefault(self, path: bytes, request: Request) -> Resource:
        return NotFoundResource('Records do not support subpaths')

    def render_GET(self, request: Request) -> bytes:
        request.setHeader(b'Content-Type', b'application/json; charset=UTF-8')
        return json.dumps(dataToJSON(self._user)).encode()

    def render_PUT(self, request: Request) -> bytes:
        # TODO: We could modify an existing user instead.
        #       The client can set "If-None-Match: *" to prevent that
        #       in cases where only creation is allowed, such as the
        #       "user add" command.
        return textReply(request, 409,
                         f"User already exists: {self._user.name}\n")

    def render_DELETE(self, request: Request) -> bytes:
        name = self._user.name
        removeUserAccount(name)
        return textReply(request, 200, f"User removed: {name}\n")

class NoUserResource(Resource):
    """HTTP resource for a non-existing user account."""

    def __init__(self, name: str):
        super().__init__()
        self._name = name

    def getChildWithDefault(self, path: bytes, request: Request) -> Resource:
        return NotFoundResource('Records do not support subpaths')

    def render_GET(self, request: Request) -> bytes:
        return textReply(request, 404, f"User not found: {self._name}\n")

    def render_PUT(self, request: Request) -> bytes:
        try:
            jsonNode = json.load(request.content)
        except json.JSONDecodeError as ex:
            return textReply(request, 400, f"Invalid JSON: {ex}\n")

        try:
            data = jsonToData(jsonNode, UserData)
        except ValueError as ex:
            return textReply(request, 400, f"Not a valid record: {ex}\n")

        name = data.name
        if name != self._name:
            return textReply(request, 400,
                             f"User name in body ({name}) does not match "
                             f"name in path ({self._name})\n")

        try:
            addUserAccount(name, uiRoleToSet(data.role))
        except ValueError as ex:
            return textReply(request, 400, f"Error creating user: {ex}\n")
        else:
            return textReply(request, 201, f"User created: {name}\n")

    def render_DELETE(self, request: Request) -> bytes:
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
            fmt = DataFormat.AUTO
        elif ext == '.json':
            fmt = DataFormat.JSON
        else:
            return NotFoundResource('Currently only ".json" is supported')

        try:
            user = userDB[name]
        except KeyError:
            return NoUserResource(name)
        else:
            return UserResource(UserData.fromUserInfo(user), fmt)

    def render_GET(self, request: Request) -> bytes:
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
        return b'User index not implemented yet\n'

def createAPIRoot() -> Resource:
    root = Resource()
    root.putChild(b'users', UsersResource())
    return root

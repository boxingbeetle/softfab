# SPDX-License-Identifier: BSD-3-Clause

"""Temporary module that contains a more RESTful API.
This should become the public API at some point, but for now it is
only used as an internal API by the command line interface.
"""

from enum import Enum, auto
from os.path import splitext
from typing import Any, Mapping, Optional, cast
from urllib.parse import unquote_plus
import json

from twisted.web.http import Request
from twisted.web.resource import IResource, Resource
import attr

from softfab.TwistedUtil import ClientErrorResource, NotFoundResource
from softfab.json import dataToJSON, jsonToData, mapJSON
from softfab.roles import UIRoleNames, uiRoleToSet
from softfab.userlib import (
    UserDB, UserInfo, addUserAccount, removePassword, removeUserAccount
)


class DataFormat(Enum):
    """The data format to use for presenting a resource."""
    AUTO = auto()
    JSON = auto()

class PasswordActions(Enum):
    """Action verbs for manipulating the password of a user account."""

    NOP = auto()
    """Do not change anything about the password."""

    REMOVE = auto()
    """Forget the current password."""

def emptyReply(request: Request) -> bytes:
    """Replies to an HTTP request with a no-body response.
    An empty bytes sequence is returned.
    """
    request.setResponseCode(204)
    request.setHeader(b'Content-Length', b'0')
    return b''

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

@attr.s(auto_attribs=True)
class UserDataUpdate(UserData):
    password: PasswordActions = PasswordActions.NOP

class UserResource(Resource):
    """HTTP resource for an existing user account."""

    def __init__(self, userDB: UserDB, user: UserData, fmt: DataFormat):
        super().__init__()
        self._userDB = userDB
        self._user = user
        self._format = fmt

    def getChildWithDefault(self, path: bytes, request: Request) -> IResource:
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

    def render_PATCH(self, request: Request) -> bytes:
        try:
            jsonNode = json.load(request.content)
        except json.JSONDecodeError as ex:
            return textReply(request, 400, f"Invalid JSON: {ex}\n")

        try:
            kwargs = mapJSON(jsonNode, UserDataUpdate)
        except ValueError as ex:
            return textReply(request, 400, f"Data mismatch: {ex}\n")

        # Get fields that can be updated.
        role = cast(Optional[UIRoleNames], kwargs.pop('role', None))
        password = cast(PasswordActions,
                        kwargs.pop('password', PasswordActions.NOP))
        if kwargs:
            return textReply(request, 400,
                             f"Patching not supported for fields: "
                             f"{', '.join(kwargs.keys())}\n")

        # Apply updates.
        userDB = self._userDB
        userName = self._user.name
        user = userDB[userName]
        if role is not None:
            user.roles = uiRoleToSet(role)
        if password is PasswordActions.REMOVE:
            removePassword(userDB, userName)

        return emptyReply(request)

    def render_DELETE(self, request: Request) -> bytes:
        name = self._user.name
        removeUserAccount(self._userDB, name)
        return textReply(request, 200, f"User removed: {name}\n")

class NoUserResource(Resource):
    """HTTP resource for a non-existing user account."""

    def __init__(self, userDB: UserDB, name: str):
        super().__init__()
        self._userDB = userDB
        self._name = name

    def getChildWithDefault(self, path: bytes, request: Request) -> IResource:
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
            addUserAccount(self._userDB, name, uiRoleToSet(data.role))
        except ValueError as ex:
            return textReply(request, 400, f"Error creating user: {ex}\n")
        else:
            return textReply(request, 201, f"User created: {name}\n")

    def render_PATCH(self, request: Request) -> bytes:
        return textReply(request, 404, f"User not found: {self._name}\n")

    def render_DELETE(self, request: Request) -> bytes:
        return textReply(request, 404, f"User not found: {self._name}\n")

class UsersResource(Resource):

    def __init__(self, userDB: UserDB):
        super().__init__()
        self._userDB = userDB

    def getChildWithDefault(self, path: bytes, request: Request) -> IResource:
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
            user = self._userDB[name]
        except KeyError:
            return NoUserResource(self._userDB, name)
        else:
            return UserResource(self._userDB, UserData.fromUserInfo(user), fmt)

    def render_GET(self, request: Request) -> bytes:
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
        return b'User index not implemented yet\n'

class APIRoot(Resource):
    """Root node for the new API."""

    ready = False

    def getChild(self, path: bytes, request: Request) -> IResource:
        if self.ready:
            return super().getChild(path, request) # 404
        else:
            return self # 503

    def render(self, request: Request) -> bytes:
        request.setHeader(b'Retry-After', b'3')
        return textReply(request, 503,
                         "API not ready yet; please try again later")

    def populate(self, dependencies: Mapping[str, Any]) -> None:
        """Add API resources under this resource."""

        self.putChild(b'users', UsersResource(dependencies['userDB']))
        self.ready = True

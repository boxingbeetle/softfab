# SPDX-License-Identifier: BSD-3-Clause

"""Temporary module that contains a more RESTful API.
This should become the public API at some point, but for now it is
only used as an internal API by the command line interface.
"""

from enum import Enum, auto
from os.path import splitext
from typing import Any, Mapping, Optional
from urllib.parse import unquote_plus
import json

from twisted.web.http import Request
from twisted.web.resource import IResource, Resource
import attr

from softfab.TwistedUtil import ClientErrorResource, NotFoundResource
from softfab.json import dataToJSON, jsonToData
from softfab.roles import UIRoleNames, uiRoleToSet
from softfab.tokens import TokenDB
from softfab.userlib import (
    UserAccount, UserDB, addUserAccount, removePassword, removeUserAccount,
    resetPassword
)
from softfab.userview import setPasswordURL


class DataFormat(Enum):
    """The data format to use for presenting a resource."""
    AUTO = auto()
    JSON = auto()

class PasswordActions(Enum):
    """Action verbs for manipulating the password of a user account."""

    REMOVE = auto()
    """Forget the current password."""

    RESET = auto()
    """Forget the current password and create a token to set a new password."""

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

def jsonReply(request: Request, data: object) -> bytes:
    """Replies to an HTTP request with data in JSON format.
    The reply body is returned.
    """
    request.setHeader(b'Content-Type', b'application/json; charset=UTF-8')
    return json.dumps(data).encode()

def _resetPasswordJSON(userDB: UserDB,
                       userName: str,
                       tokenDB: TokenDB
                       ) -> Mapping[str, str]:
    """Reset the password of a user account.
    @return: A JSON object containing the reset token and URL.
    """
    tokenCredentials = resetPassword(userDB, userName, tokenDB)
    return dict(
        token=tokenCredentials.name,
        secret=tokenCredentials.password,
        url=setPasswordURL(tokenCredentials)
        )

@attr.s(auto_attribs=True)
class UserData:
    name: str
    role: UIRoleNames

    @classmethod
    def fromUserAccount(cls, user: UserAccount) -> 'UserData':
        return cls(name=user.name, role=user.uiRole)

@attr.s(auto_attribs=True)
class UserDataCreate:
    role: UIRoleNames
    password: PasswordActions = PasswordActions.REMOVE

@attr.s(auto_attribs=True)
class UserDataUpdate:
    role: Optional[UIRoleNames] = None
    password: Optional[PasswordActions] = None

class UserResource(Resource):
    """HTTP resource for an existing user account."""

    def __init__(self,
                 userDB: UserDB,
                 tokenDB: TokenDB,
                 user: UserData,
                 fmt: DataFormat
                 ):
        super().__init__()
        self._userDB = userDB
        self._tokenDB = tokenDB
        self._user = user
        self._format = fmt

    def getChildWithDefault(self, path: bytes, request: Request) -> IResource:
        return NotFoundResource('Records do not support subpaths')

    def render_GET(self, request: Request) -> bytes:
        return jsonReply(request, dataToJSON(self._user))

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
            data = jsonToData(jsonNode, UserDataUpdate)
        except ValueError as ex:
            return textReply(request, 400, f"Data mismatch: {ex}\n")

        userDB = self._userDB
        userName = self._user.name
        user = userDB[userName]
        reply = {}

        role = data.role
        if role is not None:
            user.roles = uiRoleToSet(role)

        password = data.password
        if password is not None:
            tokenDB = self._tokenDB
            if password is PasswordActions.REMOVE:
                removePassword(userDB, userName, tokenDB)
            elif password is PasswordActions.RESET:
                reply['reset'] = _resetPasswordJSON(userDB, userName, tokenDB)

        if reply:
            return jsonReply(request, reply)
        else:
            return emptyReply(request)

    def render_DELETE(self, request: Request) -> bytes:
        name = self._user.name
        removeUserAccount(self._userDB, name, self._tokenDB)
        return textReply(request, 200, f"User removed: {name}\n")

class NoUserResource(Resource):
    """HTTP resource for a non-existing user account."""

    def __init__(self, userDB: UserDB, tokenDB: TokenDB, name: str):
        super().__init__()
        self._userDB = userDB
        self._tokenDB = tokenDB
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
            data = jsonToData(jsonNode, UserDataCreate)
        except ValueError as ex:
            return textReply(request, 400, f"Not a valid record: {ex}\n")

        userDB = self._userDB
        name = self._name
        try:
            addUserAccount(userDB, name, uiRoleToSet(data.role))
        except ValueError as ex:
            return textReply(request, 400, f"Error creating user: {ex}\n")

        reply = {}
        if data.password is PasswordActions.RESET:
            reply['reset'] = _resetPasswordJSON(userDB, name, self._tokenDB)

        if reply:
            return jsonReply(request, reply)
        else:
            return textReply(request, 201, f"User created: {name}\n")

    def render_PATCH(self, request: Request) -> bytes:
        return textReply(request, 404, f"User not found: {self._name}\n")

    def render_DELETE(self, request: Request) -> bytes:
        return textReply(request, 404, f"User not found: {self._name}\n")

class UsersResource(Resource):

    def __init__(self, userDB: UserDB, tokenDB: TokenDB):
        super().__init__()
        self._userDB = userDB
        self._tokenDB = tokenDB

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
            return NoUserResource(self._userDB, self._tokenDB, name)
        else:
            return UserResource(self._userDB, self._tokenDB,
                                UserData.fromUserAccount(user), fmt)

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

        self.putChild(b'users', UsersResource(dependencies['userDB'],
                                              dependencies['tokenDB']))
        self.ready = True

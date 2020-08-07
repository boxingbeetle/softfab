# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from pathlib import Path
from typing import Dict, Iterator, Mapping, Optional, cast

from passlib.pwd import genword

from softfab.databaselib import Database, DatabaseElem, createUniqueId
from softfab.timelib import getTime
from softfab.userlib import (
    TaskRunnerUser, UnknownUser, User, authenticate, initPasswordFile,
    writePasswordFile
)
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XML, XMLAttributeValue, xml


class TokenRole(Enum):
    """The purpose for which a token can be used.
    """
    RESOURCE = 1

class Token(XMLTag, DatabaseElem):
    """Access token that authorizes API calls to perform operations
    on behalf of a user.

    Every token can only be used for a specific subset of API calls,
    depending on its role. A token will only authorize operations that
    its owner has privileges for.
    """

    tagName = 'token'
    intProperties = ('createtime',)
    enumProperties = {'role': TokenRole}

    @classmethod
    def create(cls, role: TokenRole, params: Mapping[str, str]) -> 'Token':
        """Creates a new token.

        Before the new token can be used, a password must be set.
        """

        token = cls(dict(
            id=createUniqueId(),
            createtime=getTime(),
            role=role,
            ))
        token.__params = dict(params) # pylint: disable=protected-access
        return token

    def __init__(self, properties: Mapping[str, XMLAttributeValue]):
        self.__params: Dict[str, str] = {}
        super().__init__(properties)
        self.__owner: Optional[User] = None

    def getId(self) -> str:
        """Unique identification for this token."""
        return cast(str, self['id'])

    @property
    def createTime(self) -> int:
        """Time (in seconds since the epoch) at which this token
        was created.
        """
        return cast(int, self['createtime'])

    @property
    def role(self) -> TokenRole:
        """Role in which this token can be used."""
        return cast(TokenRole, self['role'])

    @property
    def owner(self) -> User:
        """The user that owns this token.

        Operations authorized by this token will be performed
        as this user.
        """
        owner = self.__owner
        if owner is None:
            if self.role is TokenRole.RESOURCE:
                runnerId = self.getParam('resourceId')
                owner = TaskRunnerUser(runnerId)
            else:
                owner = UnknownUser()
            self.__owner = owner
        return owner

    def getParam(self, name: str) -> str:
        """Returns the value of a parameter.

        Raises `KeyError` if there is no parameter with the given name.
        """
        return self.__params[name]

    def _addParam(self, attributes: Mapping[str, str]) -> None:
        name = attributes['name']
        value = attributes['value']
        self.__params[name] = value

    def _getContent(self) -> Iterator[XML]:
        for name, value in self.__params.items():
            yield xml.param(name=name, value=value)

class TokenFactory:
    @staticmethod
    def createToken(attributes: Mapping[str, str]) -> Token:
        return Token(attributes)

class TokenDB(Database[Token]):
    privilegeObject = 'tk'
    description = 'token'
    uniqueKeys = ('id',)

    def __init__(self, baseDir: Path):
        super().__init__(baseDir, TokenFactory())
        self.passwordFile = initPasswordFile(baseDir / 'passwords')

    def remove(self, value: Token) -> None:
        tokenId = value.getId()
        super().remove(value)
        passwordFile = self.passwordFile
        if passwordFile.delete(tokenId):
            writePasswordFile(passwordFile)

class TokenUser(User):
    """User represented by an access token.
    """

    def __init__(self, token: Token):
        super().__init__()
        self.__token = token

    @property
    def token(self) -> Token:
        return self.__token

    @property
    def name(self) -> Optional[str]:
        return self.__token.owner.name

    def hasPrivilege(self, priv: str) -> bool:
        return self.__token.owner.hasPrivilege(priv)

def authenticateToken(tokenDB: TokenDB, tokenId: str, password: str) -> Token:
    """Looks up a token with the give ID and password.

    Returns the token if the password was correct.
    Raises `KeyError` if the token does not exist.
    Raises `UnauthorizedLogin` if the password is incorrect.
    """

    # Unlike for users, we will report when a token does not exist.
    # Since tokens use strong passwords, we can afford to be more
    # user friendly here.
    token = tokenDB[tokenId]

    authenticate(tokenDB.passwordFile, tokenId, password)

    return token

def resetTokenPassword(tokenDB: TokenDB, token: Token) -> str:
    """Sets the password for this token to a new random string.

    Returns the new password. Since only a hash is stored in the
    password database, it is not possible to retrieve it later.
    """
    password = genword(length=16)
    passwordFile = tokenDB.passwordFile
    passwordFile.load_if_changed()
    passwordFile.set_password(token.getId(), password)
    writePasswordFile(passwordFile)
    return password

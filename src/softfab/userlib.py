# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
from typing import (
    Any, FrozenSet, Iterable, Iterator, Mapping, Optional, Set, Union, cast
)
import logging

from passlib.apache import HtpasswdFile
from twisted.cred.error import UnauthorizedLogin

from softfab.databaselib import Database, DatabaseElem
from softfab.roles import UIRoleNames, roleNames
from softfab.timelib import secondsPerDay
from softfab.tokens import Token, TokenDB, TokenRole, resetTokenPassword
from softfab.users import (
    Credentials, User, authenticate, checkPassword, initPasswordFile,
    rolesGrantPrivilege, writePasswordFile
)
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XML, xml


class UserAccount(XMLTag, DatabaseElem, User):
    tagName = 'user'

    def __init__(self, properties: Mapping[str, str]):
        super().__init__(properties)
        self.__roles: Union[FrozenSet[str], Set[str]] = set()

    def __getitem__(self, key: str) -> Any:
        if key == 'uirole':
            return self.uiRole
        else:
            return XMLTag.__getitem__(self, key)

    def _addRole(self, attributes: Mapping[str, str]) -> None:
        name = attributes['name']
        assert name in roleNames
        cast(Set[str], self.__roles).add(name)

    def _endParse(self) -> None:
        self.__roles = frozenset(self.__roles)

    @property
    def roles(self) -> Iterable[str]:
        return self.__roles

    @roles.setter
    def roles(self, roles: Iterable[str]) -> None:
        roles = frozenset(roles)
        if roles - roleNames:
            raise ValueError('Unknown role(s): ' + ', '.join(
                f'"{role}"' for role in sorted(roles - roleNames)
                ))
        if roles != self.__roles:
            self.__roles = roles
            self._notify()

    @property
    def uiRole(self) -> UIRoleNames:
        """Returns the most privileged role the user has, or "inactive" if the
        user does not have any roles.
        In the database, a user can have multiple roles. This is a flexible
        design, but we do not currently need all that flexibility.
        This function translates a set of roles to a single word.
        """
        roles = self.__roles
        if roles:
            return max(
                UIRoleNames.__members__[role.upper()]
                for role in roles
                )
        else:
            return UIRoleNames.INACTIVE

    @property
    def passwordResetToken(self) -> Optional[str]:
        """The ID of the token that allows a password reset for this user,
        or None if no such token exists.
        """
        return cast(Optional[str], self.get('resettoken'))

    @passwordResetToken.setter
    def passwordResetToken(self, tokenId: Optional[str]) -> None:
        if tokenId is None:
            self._properties.pop('resettoken', None)
        else:
            self._properties['resettoken'] = tokenId
        self._notify()

    def getId(self) -> str:
        return self['id']

    @property
    def name(self) -> str:
        return self.getId()

    def isInRole(self, role: str) -> bool:
        return role in self.__roles

    def hasPrivilege(self, priv: str) -> bool:
        return rolesGrantPrivilege(self.__roles, priv)

    def isActive(self) -> bool:
        '''Returns True iff this user is assigned one or more roles.
        Inactive users are not allowed to be logged in.
        '''
        return bool(self.__roles)

    def _getContent(self) -> Iterator[XML]:
        for role in self.__roles:
            yield xml.role(name = role)

class UserAccountFactory:
    @staticmethod
    def createUser(attributes: Mapping[str, str]) -> UserAccount:
        return UserAccount(attributes)

class UserDB(Database[UserAccount]):
    privilegeObject = 'u'
    description = 'user'
    uniqueKeys = ( 'id', )

    def __init__(self, baseDir: Path):
        super().__init__(baseDir, UserAccountFactory())
        self.passwordFile = initPasswordFile(baseDir.parent / 'passwords')

    @property
    def numActiveUsers(self) -> int:
        """The number of user accounts in this factory, excluding accounts
        that are no longer allowed to login.
        """
        return sum(user.isActive() for user in self)

    @property
    def showOwners(self) -> bool:
        """Should owners be shown in the user interface?

        Returns True iff there are multiple active users.
        """
        return self.numActiveUsers > 1

def addUserAccount(userDB: UserDB, userName: str, roles: Iterable[str]) -> None:
    '''Creates a new user account.
    @param userName: The name of the new user account.
    @param roles: The initial roles for the new user.
    @raise ValueError: If the user already exists,
      or the user name is syntactically invalid.
    '''
    # Check user name.
    try:
        userDB.checkId(userName)
    except KeyError as ex:
        raise ValueError(str(ex)) from ex
    if userName in userDB:
        raise ValueError(f'User "{userName}" already exists')

    # Create user record.
    userInfo = UserAccount({'id': userName})
    userInfo.roles = roles
    userDB.add(userInfo)

def _removePasswordEntry(passwordFile: HtpasswdFile, name: str) -> None:
    """Remove an entry from a password file."""

    passwordFile.load_if_changed()
    passwordFile.delete(name)
    writePasswordFile(passwordFile)

def _dropPasswordResetToken(user: UserAccount, tokenDB: TokenDB) -> None:
    """If the give user account has an active password reset token,
    remove that token and the account's link to it.
    """

    tokenId = user.passwordResetToken
    if tokenId is None:
        return

    try:
        token = tokenDB[tokenId]
    except KeyError:
        logging.warning(
            'Old password reset token %s for user "%s" did not exist',
            tokenId, user.getId()
            )
    else:
        tokenDB.remove(token)

    user.passwordResetToken = None

def removeUserAccount(userDB: UserDB, name: str, tokenDB: TokenDB) -> None:
    """Remove a user account."""

    user = userDB[name]
    # Revoke all roles, to make sure active sessions of this user will not
    # have any permissions.
    user.roles = ()
    _dropPasswordResetToken(user, tokenDB)
    _removePasswordEntry(userDB.passwordFile, name)
    userDB.remove(user)

def removePassword(userDB: UserDB,
                    name: str,
                    tokenDB: TokenDB
                    ) -> None:
    """Remove an account's current password."""

    user = userDB[name]
    _dropPasswordResetToken(user, tokenDB)
    _removePasswordEntry(userDB.passwordFile, name)

passwordResetDays = 7
"""The number of days a password reset token is valid."""

def resetPassword(userDB: UserDB, name: str, tokenDB: TokenDB) -> Credentials:
    """Remove an account's current password and create a token that
    allows setting a new password.
    @return: The credentials of the password reset token.
    """

    removePassword(userDB, name, tokenDB)

    token = Token.create(TokenRole.PASSWORD_RESET, {'name': name},
                         expireSecs=passwordResetDays * secondsPerDay)
    tokenDB.add(token)
    tokenId = token.getId()
    userDB[name].passwordResetToken = tokenId

    tokenPassword = resetTokenPassword(tokenDB, token)
    return Credentials(tokenId, tokenPassword)

def setPassword(userDB: UserDB, credentials: Credentials) -> None:
    '''Sets the password for an existing user account.
    @param credentials: The user name and new password.
    @raise ValueError: If the user does not exist in the database,
      or the password is syntactically invalid.
    '''

    userName = credentials.name
    password = credentials.password

    # Sanity check on user name.
    if userName not in userDB:
        raise ValueError(f'User "{userName}" does not exist')

    # Check password.
    checkPassword(password)

    # Commit the new password.
    passwordFile = userDB.passwordFile
    passwordFile.load_if_changed()
    passwordFile.set_password(userName, password)
    writePasswordFile(passwordFile)

async def authenticateUser(userDB: UserDB,
                           credentials: Credentials
                           ) -> UserAccount:
    """Authenticates a user with the given password.

    Callback arguments: user object for the authenticated user.
    Errback: `UnauthorizedLogin` if the given user name and password
             combination is not accepted.
             `LoginFailed` if there was an internal error.
    """

    # Twisted returns empty string if there is no "authorization" header,
    # it would be a waste of time to look that up in the password file.
    userName = credentials.name
    if not userName:
        raise UnauthorizedLogin('No user name specified')

    authenticate(userDB.passwordFile, credentials)

    try:
        return userDB[userName]
    except KeyError:
        logging.warning(
            'User "%s" exists in the password file but not in the user DB',
            userName
            )
        # Note: We return the same error as for an incorrect password,
        #       to reduce the chance attackers learn anything helpful.
        raise UnauthorizedLogin('Authentication failed')

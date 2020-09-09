# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
from typing import (
    Any, FrozenSet, Iterable, Iterator, Mapping, Set, Union, cast
)
import logging

from twisted.cred.error import UnauthorizedLogin

from softfab.databaselib import Database, DatabaseElem
from softfab.roles import UIRoleNames, roleNames
from softfab.users import (
    User, authenticate, checkPassword, initPasswordFile, rolesGrantPrivilege,
    writePasswordFile
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

def removeUserAccount(userDB: UserDB, name: str) -> None:
    """Remove a user account."""

    user = userDB[name]
    # Revoke all roles prior to removal, to make sure active sessions
    # of this user will not have any permissions.
    user.roles = ()
    userDB.remove(user)

    removePassword(userDB, name)

def removePassword(userDB: UserDB, name: str) -> None:
    """Remove an account's password."""

    passwordFile = userDB.passwordFile
    passwordFile.load_if_changed()
    passwordFile.delete(name)
    writePasswordFile(passwordFile)

def setPassword(userDB: UserDB, userName: str, password: str) -> None:
    '''Sets the password for an existing user account.
    @param userName: The name of the user account.
    @param password: New password for the user.
    @raise ValueError: If the user does not exist in the database,
      or the password is syntactically invalid.
    '''

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
                           userName: str,
                           password: str
                           ) -> UserAccount:
    """Authenticates a user with the given password.

    Callback arguments: user object for the authenticated user.
    Errback: `UnauthorizedLogin` if the given user name and password
             combination is not accepted.
             `LoginFailed` if there was an internal error.
    """

    # Twisted returns empty string if there is no "authorization" header,
    # it would be a waste of time to look that up in the password file.
    if not userName:
        raise UnauthorizedLogin('No user name specified')

    authenticate(userDB.passwordFile, userName, password)

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

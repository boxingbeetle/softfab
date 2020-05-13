# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from enum import Enum
from os import makedirs
from os.path import dirname, exists
from typing import (
    Any, FrozenSet, Iterable, Iterator, Mapping, Optional, Sequence, Set,
    Tuple, Union, cast
)
import logging

from passlib.apache import HtpasswdFile
from twisted.cred.error import LoginFailed, UnauthorizedLogin

from softfab.compat import Protocol
from softfab.config import dbDir
from softfab.databaselib import Database, DatabaseElem
from softfab.roles import UIRoleNames, roleNames
from softfab.utils import atomicWrite, iterable
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XML, xml

# Privileges are designated as '<object>/<action>' where object can be:
#   j(job), t(task), c(config), td(task definition),
#   fd(framework definition), pd(product definition), tk(token),
#   tr(Task Runner), rt (resource type), r(resource), p(project), s(schedule),
#   sp(storage pool), u(user)
# and action can be:
#   l(list), c(create), a(access), m(modify), d(delete)
# Action with 'o' suffix (e.g. 'mo') means that the object it is applied
#   to is owned by the current user (thus different access rights may apply)

privileges: Mapping[str, Sequence[str]] = {
    'j/l': ('guest', 'user', 'operator'),
    'j/c': ('user', 'operator'),
    'j/a': ('guest', 'user', 'operator'),
#    'j/m': (),
#    'j/d': (),

    't/l': ('guest', 'user', 'operator'),
#    't/c': (),
    't/a': ('guest', 'user', 'operator'),
    't/m': ('user', 'operator'),
    't/d': ('operator', ),
    't/do': ('user', 'operator'),

    'c/l': ('guest', 'user', 'operator'),
    'c/c': ('user', 'operator'),
    'c/a': ('guest', 'user', 'operator'),
    'c/m': ('operator', ),
    'c/mo': ('user', 'operator'),
    'c/d': ('operator', ),
    'c/do': ('user', 'operator'),

    'td/l': ('guest', 'user', 'operator'),
    'td/c': ('operator', ),
    'td/a': ('guest', 'user', 'operator'),
    'td/m': ('operator', ),
    'td/d': ('operator', ),

    'fd/l': ('guest', 'user', 'operator'),
    'fd/c': ('operator', ),
    'fd/a': ('guest', 'user', 'operator'),
    'fd/m': ('operator', ),
    'fd/d': ('operator', ),

    'pd/l': ('guest', 'user', 'operator'),
    'pd/c': ('operator', ),
    'pd/a': ('guest', 'user', 'operator'),
    'pd/m': ('operator', ),
    'pd/d': ('operator', ),

    'tk/l': ('user', 'operator'),
    'tk/c': ('user', 'operator'),
    'tk/a': ('user', 'operator'),
    'tk/m': ('user', 'operator'),
    'tk/d': ('user', 'operator'),

    'rt/l': ('guest', 'user', 'operator'),
    'rt/c': ('operator', ),
    'rt/a': ('guest', 'user', 'operator'),
    'rt/m': ('operator', ),
    'rt/d': ('operator', ),

    # Note: Reservation is controlled by the 'r/a' privilege;
    #       'r/m' controls the resource definition.
    'r/l': ('guest', 'user', 'operator'),
    'r/c': ('operator', ),
    'r/a': ('user', 'operator'),
    'r/m': ('operator', ),
    'r/d': ('operator', ),

    's/l': ('guest', 'user', 'operator'),
    's/c': ('user', 'operator'),
    's/a': ('guest', 'user', 'operator'),
    's/m': ('operator', ),
    's/mo': ('user', 'operator'),
    's/d': ('operator', ),
    's/do': ('user', 'operator'),

    'sp/l': ('guest', 'user', 'operator'),
    'sp/a': ('guest', 'user', 'operator'),
    #'sp/c': (),
    'sp/m': ('operator', ),
    #'sp/d': ('operator', ),

    'u/l': ('guest', 'user', 'operator'),
    'u/c': ('operator', ),
#    'u/a': ('user', 'operator'),
    'u/m': ('operator', ),
    'u/mo': ('user', 'operator', ),
    'u/d': ('operator', ),

# There is always exactly 1 record in project DB,
# so list/create/delete do not apply.
#    'p/l': (),
#    'p/c': (),
    'p/a': ('guest', 'user', 'operator'),
    'p/m': ('operator', ),
#    'p/d': (),

    # Privileges not tied to DB records:
    'sysver': ('operator', ), # View system version information.

    # Privileges that are only granted by tokens:
    'tr/*': (), # Non-standard privilege used by Task Runners.

}

def rolesGrantPrivilege(roles: Iterable[str], priv: str) -> bool:
    return any(role in roles for role in privileges[priv])

PasswordMessage = Enum('PasswordMessage', 'SUCCESS POOR SHORT EMPTY MISMATCH')
'''Reasons for rejecting a password.
'''

minimumPasswordLength = 8

def initPasswordFile(path: str) -> HtpasswdFile:
    passwordFile = HtpasswdFile(path, default_scheme='portable', new=True)

    # Marking schemes as deprecated tells passlib to re-hash when a password
    # is successfully verified. Instead of marking only known insecure schemes
    # as deprecated, we mark everything except the default scheme.
    # A good password cannot be brute forced in a reasonable amount of time,
    # but few people actually use good passwords, so slowing down an attacker
    # by using the best hash algorithm we have available is useful.
    orgContext = passwordFile.context
    defaultScheme = orgContext.default_scheme()
    deprecated = [
        scheme for scheme in orgContext.schemes() if scheme != defaultScheme
        ]
    passwordFile.context = orgContext.copy(deprecated=deprecated)

    try:
        passwordFile.load()
    except FileNotFoundError:
        dirPath = dirname(path)
        if not exists(dirPath):
            makedirs(dirPath)
        # Create empty file.
        with open(path, 'a'):
            pass

    return passwordFile

def writePasswordFile(passwordFile: HtpasswdFile) -> None:
    # Note: Despite the name, to_string() returns bytes.
    data = passwordFile.to_string()
    with atomicWrite(passwordFile.path, 'wb') as out:
        out.write(data)

_passwordFile = initPasswordFile(dbDir + '/passwords')

async def authenticateUser(userName: str, password: str) -> 'UserInfo':
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

    authenticate(_passwordFile, userName, password)

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

def authenticate(passwordFile: HtpasswdFile, name: str, password: str) -> None:
    """Checks a name and password combination against a password file.

    Returns if authentication succeeds.
    Raises `UnauthorizedLogin` if the given user name and password
    combination is not accepted.

    The hashed version of the password will be updated with a new
    hash function if the current one is depricated.
    """

    try:
        _checkPassword(password)
    except ValueError as ex:
        raise UnauthorizedLogin(ex) from ex

    # Have passlib check the password. When passed a None hash, it will
    # perform a dummy computation to keep the timing consistent.
    passwordFile.load_if_changed()
    correct, newHash = passwordFile.context.verify_and_update(
        password.encode(), passwordFile.get_hash(name)
        )
    if not correct:
        raise UnauthorizedLogin('Authentication failed')

    if newHash is not None:
        # Replace hash with better algorithm or config.
        passwordFile.set_hash(name, newHash)
        writePasswordFile(passwordFile)

def _checkPassword(password: str) -> None:
    '''Checks whether the given password is valid.
    Does nothing if the password is valid; raises ValueError otherwise.
    '''
    if not password:
        raise ValueError('Empty password is not allowed')
    invalidCodes = [
        ord(ch)
        for ch in password
        if not (32 <= ord(ch) < 127)
        ]
    if invalidCodes:
        raise ValueError(
            'The password contains invalid character codes: ' +
            ', '.join(f'{code:d}' for code in sorted(invalidCodes))
            )

def addUserAccount(userName: str, roles: Iterable[str]) -> None:
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
    userInfo = UserInfo({'id': userName})
    userInfo.roles = roles
    userDB.add(userInfo)

def setPassword(userName: str, password: str) -> None:
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
    _checkPassword(password)

    # Commit the new password.
    _passwordFile.load_if_changed()
    _passwordFile.set_password(userName, password)
    writePasswordFile(_passwordFile)

def passwordQuality(userName: str, password: str) -> PasswordMessage:
    '''Performs sanity checks on a username/password combination.
    '''
    if not password:
        return PasswordMessage.EMPTY

    if len(password) < minimumPasswordLength:
        return PasswordMessage.SHORT

    if userName == password:
        return PasswordMessage.POOR

    return PasswordMessage.SUCCESS

class User(ABC):
    '''A user account.
    '''

    @property
    def name(self) -> Optional[str]:
        '''Login name of the user account, or None for anonymous users.
        '''
        raise NotImplementedError

    def hasPrivilege(self, priv: str) -> bool:
        '''Returns True iff this user has the given privilege.
        '''
        raise NotImplementedError

class TaskRunnerUser(User):
    '''Identifies a Task Runner making API calls.
    '''

    def __init__(self, runnerId: str):
        super().__init__()
        self.__runnerId = runnerId

    @property
    def name(self) -> str:
        return self.__runnerId

    def hasPrivilege(self, priv: str) -> bool:
        return priv == 'tr/*'

class SuperUser(User):
    '''Anonymous user who has the combined privileges of all roles.
    '''

    @property
    def name(self) -> Optional[str]:
        return None

    def hasPrivilege(self, priv: str) -> bool:
        return bool(privileges[priv])

class AnonGuestUser(User):
    '''Anonymous user who has guest privileges.
    '''

    @property
    def name(self) -> Optional[str]:
        return None

    def hasPrivilege(self, priv: str) -> bool:
        return 'guest' in privileges[priv]

class UnknownUser(User):
    '''Anonymous user who has no privileges.
    '''

    @property
    def name(self) -> Optional[str]:
        return None

    def hasPrivilege(self, priv: str) -> bool:
        return False

class UserInfoFactory:
    @staticmethod
    def createUser(attributes: Mapping[str, str]) -> 'UserInfo':
        return UserInfo(attributes)

class UserDB(Database['UserInfo']):
    baseDir = dbDir + '/users'
    factory = UserInfoFactory()
    privilegeObject = 'u'
    description = 'user'
    uniqueKeys = ( 'id', )

    @property
    def numActiveUsers(self) -> int:
        """The number of user accounts in this factory, excluding accounts
        that are no longer allowed to login.
        """
        return sum(user.isActive() for user in self)

userDB = UserDB()

class UserInfo(XMLTag, DatabaseElem, User):
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

class AccessDenied(Exception):
    pass

def checkPrivilege(user: User, priv: str, text: Optional[str] = None) -> None:
    if not user.hasPrivilege(priv):
        if text is None:
            raise AccessDenied()
        else:
            raise AccessDenied(text)

class Owned(Protocol):
    @property
    def owner(self) -> Optional[str]: ...

def checkPrivilegeForOwned(
        user: User,
        priv: str,
        owned: Union[Owned, Iterable[Owned]],
        text: Union[None, str, Tuple[str, str]] = None
        ) -> None:
    '''Checks whether a user is allowed to perform an action on an owned
    database record.
    @param owned Record or sequence of records to test for ownership.
    @param text String to display if the user is not allowed to perform
        the action, or a tuple of which the first element is the string to
        display if the user is not allowed to perform the action on this
        particular record and the second element is the string to display
        if the user is not allowed to perform the action on any record
        of this type.
    '''
    assert not priv.endswith('o'), priv
    if user.hasPrivilege(priv):
        # User is allowed to take action also for non-owned records.
        return
    ownedPriv = priv + 'o'
    hasOwnedPriv = ownedPriv in privileges and user.hasPrivilege(ownedPriv)
    if hasOwnedPriv:
        # User is allowed to perform action, but only for owned records.
        userName = user.name
        if iterable(owned):
            if all(rec.owner == userName
                   for rec in cast(Iterable[Owned], owned)):
                return
        else:
            if cast(Owned, owned).owner == userName:
                return
    # Construct error message.
    if isinstance(text, tuple):
        text = text[0 if hasOwnedPriv else 1]
    if text is None:
        raise AccessDenied()
    else:
        raise AccessDenied(text)

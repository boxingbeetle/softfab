# SPDX-License-Identifier: BSD-3-Clause

from softfab.datawidgets import DataColumn
from softfab.pageargs import EnumArg, PageArgs, PasswordArg
from softfab.pagelinks import UserIdArgs, createUserDetailsLink
from softfab.userlib import UIRoleNames, PasswordMessage, minimumPasswordLength

passwordStr = {
    PasswordMessage.SUCCESS  : 'The password has been changed successfully.',
    PasswordMessage.POOR      : 'This password is not secure.',
    PasswordMessage.SHORT      : 'The password must be at least %d characters.'
                                % minimumPasswordLength,
    PasswordMessage.EMPTY      : 'An empty password is not allowed.',
    PasswordMessage.MISMATCH : 'New password mismatch.',
    }

class PasswordMsgArgs(UserIdArgs):
    '''Identifies a particular user (mandatory) and password message (optional).
    '''
    msg = EnumArg(PasswordMessage, None)

class LoginPassArgs(PageArgs):
    # Note: Sharing the argument name between the Login page and other pages
    #       requiring the user to type his/her password allows the browser to
    #       fill in the login password automatically. This does not work in all
    #       browsers, since some fill forms only when there is an URL match
    #       while others only require a site match. But having to type the
    #       password is not a critical inconvenience.
    #       Using a stored password does not compromise security any more
    #       than storing the password in the first place.
    loginpass = PasswordArg()

def activeRole(user):
    '''Returns the most privileged role the user has, or "inactive" if the user
    does not have any roles.
    In the database, a user can have multiple roles. This is a flexible design,
    but we do not currently need all that flexibility. This function translates
    a set of roles to a single word.
    '''
    roles = user['roles']
    return max(roles) if roles else UIRoleNames.INACTIVE

def uiRoleToSet(role):
    '''The opposite transformation of activeRole().
    '''
    assert role in UIRoleNames
    return set() if role is UIRoleNames.INACTIVE else { role.name.lower() }

class OwnerColumn(DataColumn):
    keyName = 'owner'
    def presentCell(self, record, **kwargs):
        owner = record['owner']
        return '-' if owner is None else createUserDetailsLink(owner)

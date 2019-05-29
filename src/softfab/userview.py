# SPDX-License-Identifier: BSD-3-Clause

from softfab.datawidgets import DataColumn
from softfab.pageargs import EnumArg, PageArgs, PasswordArg
from softfab.pagelinks import UserIdArgs, createUserDetailsLink
from softfab.projectlib import project
from softfab.userlib import PasswordMessage, UIRoleNames, minimumPasswordLength
from softfab.xmlgen import xhtml

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

def uiRoleToSet(role):
    '''The opposite transformation of `UserInfo.uiRole`.
    '''
    assert role in UIRoleNames
    return set() if role is UIRoleNames.INACTIVE else { role.name.lower() }

def presentAnonGuestSetting():
    return xhtml.p[
        'Anonymous guest access is ',
        xhtml.b['enabled' if project['anonguest'] else 'disabled'], '.'
        ]

class OwnerColumn(DataColumn):
    keyName = 'owner'
    def presentCell(self, record, **kwargs):
        owner = record['owner']
        return '-' if owner is None else createUserDetailsLink(owner)

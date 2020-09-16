# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import cast

from softfab.config import rootURL
from softfab.datawidgets import DataColumn
from softfab.pageargs import EnumArg, PageArgs, PasswordArg
from softfab.pagelinks import PasswordSetArgs, createUserDetailsLink
from softfab.projectlib import Project
from softfab.querylib import Record
from softfab.userlib import passwordResetDays
from softfab.webgui import pageURL
from softfab.xmlgen import XMLContent, xhtml

PasswordMessage = Enum('PasswordMessage', 'SUCCESS POOR SHORT EMPTY MISMATCH')
'''Reasons for rejecting a password.
'''

minimumPasswordLength = 8

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

passwordStr = {
    PasswordMessage.SUCCESS  : 'The password has been changed successfully.',
    PasswordMessage.POOR     : 'This password is not secure.',
    PasswordMessage.SHORT    : 'The password must be at least '
                                    f'{minimumPasswordLength:d} characters.',
    PasswordMessage.EMPTY    : 'An empty password is not allowed.',
    PasswordMessage.MISMATCH : 'New password mismatch.',
    }

class PasswordMsgArgs(PageArgs):
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

def presentSetPasswordURL(
        userName: str,
        tokenId: str,
        tokenPassword: str
        ) -> XMLContent:
    url = rootURL + pageURL('SetPassword',
        PasswordSetArgs(token=tokenId, secret=tokenPassword))
    yield xhtml.p[
        "Please send the following URL to ", xhtml.b[ userName ], ":"
        ]
    yield xhtml.p[ xhtml.code[ url ] ]
    yield xhtml.p[
        f"The URL can be used to set a new password once "
        f"and is valid for {passwordResetDays} days."
        ]

def presentAnonGuestSetting(project: Project) -> XMLContent:
    return xhtml.p[
        'Anonymous guest access is ',
        xhtml.b['enabled' if project.anonguest else 'disabled'], '.'
        ]

class OwnerColumn(DataColumn[Record]):
    keyName = 'owner'
    def presentCell(self, record: Record, **kwargs: object) -> XMLContent:
        owner = cast(str, record['owner'])
        return '-' if owner is None else createUserDetailsLink(owner)

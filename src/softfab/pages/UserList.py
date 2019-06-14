# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.datawidgets import DataColumn, DataTable
from softfab.formlib import (
    SingleCheckBoxTable, dropDownList, hiddenInput, makeForm, submitButton
)
from softfab.pageargs import (
    BoolArg, EnumArg, IntArg, PageArgs, SortArg, StrArg
)
from softfab.pagelinks import AnonGuestArgs, UserIdArgs, createUserDetailsLink
from softfab.projectlib import project
from softfab.querylib import CustomFilter
from softfab.userlib import (
    UIRoleNames, User, UserInfo, checkPrivilege, rolesGrantPrivilege, userDB
)
from softfab.userview import presentAnonGuestSetting, uiRoleToSet
from softfab.webgui import pageLink, pageURL, script
from softfab.xmlgen import XML, XMLContent, xhtml


class NameColumn(DataColumn[UserInfo]):
    label = 'Name'
    keyName = 'id'
    def presentCell(self, record, **kwargs):
        return createUserDetailsLink(record.getId())

roleDropDownList = dropDownList(name='role')[ UIRoleNames ]

class RoleColumn(DataColumn[UserInfo]):
    label = 'Role'
    keyName = 'uirole'

    def presentCell(self, record, *, proc, **kwargs):
        role = record.uiRole
        if proc.canChangeRoles:
            userName = record.getId()
            return makeForm(
                formId = 'role_%s' % userName,
                args = proc.args,
                setFocus = False
                )[
                hiddenInput(name='user', value=userName),
                roleDropDownList(selected=role), ' ', submitButton[ 'Apply' ]
                ].present(proc=proc, **kwargs)
        else:
            return role

class PasswordColumn(DataColumn[UserInfo]):
    label = 'Password'

    def presentCell(self, record, *, proc, **kwargs):
        requestUser = proc.user
        userName = record.getId()
        if requestUser.hasPrivilege('u/m') or (
                requestUser.hasPrivilege('u/mo') and
                requestUser.name == userName
                ):
            # User is allowed to modify passwords.
            return pageLink('ChangePassword', UserIdArgs(user = userName))[
                'Change'
                ]
        else:
            return None

class FilterTable(SingleCheckBoxTable):
    name = 'inactive'
    label = 'Show inactive users'

    def iterRows(self, **kwargs):
        yield from super().iterRows(**kwargs)
        yield submitButton[ 'Apply' ].present(**kwargs),

class AnonGuestTable(SingleCheckBoxTable):
    name = 'anonguest'
    label = 'Anonymous guest access'

    def iterRows(self, **kwargs):
        yield from super().iterRows(**kwargs)
        yield (
            'This grants visitors that are not logged in read-only access '
            'to your SoftFab.'
            ),
        yield submitButton[ 'Apply' ].present(**kwargs),

class UserTable(DataTable[UserInfo]):
    db = userDB
    objectName = 'users'

    def iterFilters(self, proc):
        if not proc.args.inactive:
            yield CustomFilter(lambda user: user.isActive())

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn[UserInfo]]:
        proc = cast(PageProcessor, kwargs['proc'])
        yield NameColumn.instance
        yield RoleColumn.instance
        requestUser = proc.user
        if requestUser.hasPrivilege('u/m') or requestUser.hasPrivilege('u/mo'):
            yield PasswordColumn.instance

# Disable each "Apply" button by default and enable it if a new role has been
# picked with the drop-down list.
roleApplyScript = script[r'''
for (var i = 0; i < document.forms.length; i++) {
    var form = document.forms[i];
    if (form.id.indexOf("role_") == 0) {
        var inputNodes = form.getElementsByTagName('input');
        var submitNode = null;
        for (var j = 0; j < inputNodes.length; j++) {
            var inputNode = inputNodes[j];
            if (inputNode.type == "submit") {
                submitNode = inputNode;
            }
        }
        if (!submitNode) continue;
        submitNode.disabled = true;
        var selectNodes = form.getElementsByTagName('select');
        for (var j = 0; j < selectNodes.length; j++) {
            var selectNode = selectNodes[j];
            selectNode.onchange = function(event) {
                this.submitNode.disabled = false;
            };
            selectNode.submitNode = submitNode;
        }
    }
}
''']

class UserList_GET(FabPage['UserList_GET.Processor', 'UserList_GET.Arguments']):
    icon = 'IconUser'
    description = 'Users'
    children = 'UserDetails', 'AddUser', 'ChangePassword', 'AnonGuest'

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'u/l')

    class Arguments(PageArgs):
        inactive = BoolArg()
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor['UserList_GET.Arguments']):

        def process(self, req, user):
            # pylint: disable=attribute-defined-outside-init
            self.canChangeRoles = user.hasPrivilege('u/m')
            self.canChangeAnonGuest = user.hasPrivilege('p/m')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield UserTable.instance

    def pageTitle(self, proc: Processor) -> str:
        return 'Configure Users'

    def presentContent(self, proc: Processor) -> XMLContent:
        yield makeForm(method = 'get', formId = 'inactive')[
            FilterTable.instance
            ].present(proc=proc)

        yield UserTable.instance.present(proc=proc)
        if proc.canChangeRoles:
            yield xhtml.p[
                'To deny an existing user access to your SoftFab, '
                'set the user\'s role to "inactive".'
                ]
            yield roleApplyScript.present(proc=proc)

        if proc.canChangeAnonGuest:
            yield makeForm(
                formId='anonguest',
                action='AnonGuest',
                setFocus=False,
                args=AnonGuestArgs(anonguest=project['anonguest'])
                )[ AnonGuestTable.instance ].present(proc=proc)
        else:
            yield presentAnonGuestSetting()

class UserList_POST(FabPage['UserList_POST.Processor',
                            'UserList_POST.Arguments']):
    icon = 'IconUser'
    description = 'Change Role'

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'u/m', 'control user accounts')

    class Arguments(UserList_GET.Arguments):
        user = StrArg()
        role = EnumArg(UIRoleNames)

    class Processor(PageProcessor['UserList_POST.Arguments']):

        def process(self, req, user):
            # Find user record.
            userName = req.args.user
            try:
                subject = userDB[userName]
            except KeyError:
                raise PresentableError(
                    xhtml.p(class_ = 'notice')[
                        'There is no user named "%s"' % userName
                        ]
                    )

            # Parse and check all changes.
            requestUserName = user.name
            newRoles = uiRoleToSet(req.args.role)
            if (userName == requestUserName
                    and not rolesGrantPrivilege(newRoles, 'u/m')):
                # Prevent user from revoking their own 'u/m' privilege.
                raise PresentableError((
                    xhtml.p(class_ = 'notice')[
                        'Revoking your own privileges could lead to '
                        'a situation from which recovery is impossible.'
                        ],
                    xhtml.p[
                        'If you want to change the role of user "%s", '
                        'please log in as another user with operator '
                        'privileges.' % userName
                        ],
                    ))

            # Changes are OK, commit them.
            subject.roles = newRoles

            raise Redirect(pageURL(
                'UserList',
                UserList_GET.Arguments.subset(req.args)
                ))

    def pageTitle(self, proc: Processor) -> str:
        return 'Change User Role'

    def presentContent(self, proc: Processor) -> XMLContent:
        assert False

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        proc = cast(UserList_POST.Processor, kwargs['proc'])
        yield message
        yield xhtml.p[
            pageLink('UserList', UserList_GET.Arguments.subset(proc.args))[
                'Back to Users'
                ]
            ]

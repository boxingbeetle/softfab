# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.config import enableSecurity
from softfab.datawidgets import DataColumn, DataTable
from softfab.formlib import (
    SingleCheckBoxTable, dropDownList, hiddenInput, makeForm, submitButton
    )
from softfab.pageargs import BoolArg, EnumArg, IntArg, PageArgs, StrArg, SortArg
from softfab.pagelinks import UserIdArgs, createUserDetailsLink
from softfab.querylib import CustomFilter
from softfab.userlib import UIRoleNames, rolesGrantPrivilege, userDB
from softfab.userview import activeRole, uiRoleToSet
from softfab.webgui import pageLink, pageURL, script
from softfab.xmlgen import xhtml

class NameColumn(DataColumn):
    label = 'Name'
    keyName = 'id'
    def presentCell(self, record, **kwargs):
        return createUserDetailsLink(record.getId())

roleDropDownList = dropDownList(name='role')[ UIRoleNames ]

class RoleColumn(DataColumn):
    label = 'Role'
    keyName = 'roles'

    def presentCell(self, record, proc, **kwargs):
        role = activeRole(record)
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

class PasswordColumn(DataColumn):
    label = 'Password'

    def presentCell(self, record, proc, **kwargs):
        requestUser = proc.req.getUser()
        userName = record.getId()
        if requestUser.hasPrivilege('u/m') or (
            requestUser.hasPrivilege('u/mo') and requestUser.getId() == userName
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

class UserTable(DataTable):
    db = userDB
    objectName = 'users'

    def iterFilters(self, proc):
        if not proc.args.inactive:
            yield CustomFilter(lambda user: user.isActive())

    def iterColumns(self, proc, **kwargs):
        yield NameColumn.instance
        yield RoleColumn.instance
        requestUser = proc.req.getUser()
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

class UserList_GET(FabPage):
    icon = 'UserList1'
    description = 'Users'
    children = 'UserDetails', 'AddUser', 'ChangePassword'
    isActive = staticmethod(lambda: enableSecurity)

    def fabTitle(self, proc):
        return 'Configure Users'

    def checkAccess(self, req):
        req.checkPrivilege('u/l')

    class Arguments(PageArgs):
        inactive = BoolArg()
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):

        def process(self, req):
            # pylint: disable=attribute-defined-outside-init
            self.canChangeRoles = req.getUser().hasPrivilege('u/m')

    def iterDataTables(self, proc):
        yield UserTable.instance

    def presentContent(self, proc):
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

class UserList_POST(FabPage):
    icon = 'UserList1'
    description = 'Change Role'
    isActive = staticmethod(lambda: enableSecurity)

    def fabTitle(self, proc):
        return 'Change User Role'

    def checkAccess(self, req):
        req.checkPrivilege('u/m', 'control user accounts')

    class Arguments(UserList_GET.Arguments):
        user = StrArg()
        role = EnumArg(UIRoleNames)

    class Processor(PageProcessor):

        def process(self, req):
            # Find user record.
            userName = req.args.user
            try:
                user = userDB[userName]
            except KeyError:
                raise PresentableError(
                    xhtml.p(class_ = 'notice')[
                        'There is no user named "%s"' % userName
                        ]
                    )

            # Parse and check all changes.
            requestUserName = req.getUserName()
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
            user.setRoles(newRoles)

            raise Redirect(pageURL(
                'UserList',
                UserList_GET.Arguments.subset(req.args)
                ))

    def presentContent(self, proc):
        assert False

    def presentError(self, proc, message):
        yield message
        yield xhtml.p[
            pageLink('UserList', UserList_GET.Arguments.subset(proc.args))[
                'Back to Users'
                ]
            ]
# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.ReportMixin import ReportArgs
from softfab.datawidgets import DataTable
from softfab.joblib import jobDB
from softfab.jobview import JobsSubTable
from softfab.pageargs import PageArgs, StrArg
from softfab.pagelinks import UserIdArgs
from softfab.querylib import KeySorter, ValueFilter, runQuery
from softfab.userlib import User, userDB
from softfab.userview import activeRole
from softfab.webgui import PropertiesTable, Widget, pageLink
from softfab.xmlgen import XMLContent, xhtml


class DetailsTable(PropertiesTable):

    def iterRows(self, *, proc, **kwargs):
        yield 'Role', activeRole(proc.infoUser)

class OwnedJobsTable(JobsSubTable):
    widgetId = 'jobsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc):
        return proc.jobs

class UserDetails_GET(FabPage['UserDetails_GET.Processor', 'UserDetails_GET.Arguments']):
    icon = 'UserList1'
    description = 'User Details'

    class Arguments(PageArgs):
        user = StrArg()

    class Processor(PageProcessor):
        visibleJobs = 12

        def process(self, req):
            infoUserName = req.args.user

            infoUser = userDB.get(infoUserName)
            jobs = runQuery(
                [ ValueFilter('owner', infoUserName, jobDB),
                  KeySorter([ 'recent' ], jobDB)
                  ],
                jobDB
                )[ : self.visibleJobs]

            # pylint: disable=attribute-defined-outside-init
            self.infoUser = infoUser
            self.jobs = jobs

    def checkAccess(self, user: User) -> None:
        pass

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        yield OwnedJobsTable.instance

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield OwnedJobsTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
        infoUser = proc.infoUser
        infoUserName = proc.args.user
        requestUser = proc.req.user
        requestUserName = requestUser.getUserName()

        if infoUser is None:
            yield xhtml.p[
                'User ', xhtml.b[ infoUserName ], ' does not exist.'
                ]
            return

        yield xhtml.h2[ 'Details of user ', xhtml.b[ infoUserName ], ':' ]
        yield DetailsTable.instance.present(proc=proc)

        if infoUserName == requestUserName:
            if requestUser.hasPrivilege('u/mo'):
                yield xhtml.p[
                    pageLink(
                        'ChangePassword',
                        UserIdArgs(user = requestUserName)
                        )[ 'Change your password' ]
                    ]

        yield xhtml.h2[ 'Recent jobs:' ]
        yield OwnedJobsTable.instance.present(proc=proc)

        reportOwnerArgs = ReportArgs(owner = set([ infoUserName ]))
        yield xhtml.p[
            pageLink('ReportIndex', reportOwnerArgs)[
                'Show all jobs owned by %s' % infoUserName
                ]
            ]
        yield xhtml.p[
            pageLink('ReportTasks', reportOwnerArgs)[
                'Show tasks owned by %s' % infoUserName
                ]
            ]

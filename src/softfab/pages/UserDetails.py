# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.ReportMixin import ReportArgs
from softfab.config import enableSecurity
from softfab.joblib import jobDB
from softfab.jobview import JobsSubTable
from softfab.pageargs import PageArgs, StrArg
from softfab.pagelinks import UserIdArgs
from softfab.querylib import KeySorter, ValueFilter, runQuery
from softfab.userlib import userDB
from softfab.userview import activeRole
from softfab.webgui import PropertiesTable, pageLink
from softfab.xmlgen import xhtml

class DetailsTable(PropertiesTable):

    def iterRows(self, proc, **kwargs):
        yield 'Role', activeRole(proc.infoUser)

class OwnedJobsTable(JobsSubTable):
    widgetId = 'jobsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc):
        return proc.jobs

class UserDetails(FabPage):
    icon = 'UserList1'
    description = 'User Details'
    isActive = staticmethod(lambda: enableSecurity)

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

    def checkAccess(self, req):
        pass

    def iterWidgets(self, proc):
        yield OwnedJobsTable

    def iterDataTables(self, proc):
        yield OwnedJobsTable.instance

    def presentContent(self, proc):
        infoUser = proc.infoUser
        infoUserName = proc.args.user
        requestUser = proc.req.getUser()
        requestUserName = requestUser.getId()

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
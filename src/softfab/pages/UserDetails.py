# SPDX-License-Identifier: BSD-3-Clause

from typing import Any, ClassVar, Collection, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError
from softfab.datawidgets import DataTable
from softfab.joblib import Job, JobDB
from softfab.jobview import JobsSubTable
from softfab.pageargs import PageArgs, StrArg
from softfab.pagelinks import ReportArgs
from softfab.querylib import KeySorter, ValueFilter, runQuery
from softfab.request import Request
from softfab.schedulelib import ScheduleDB
from softfab.userlib import User, UserDB
from softfab.webgui import PropertiesTable, Widget, pageLink
from softfab.xmlgen import XML, XMLContent, xhtml


class DetailsTable(PropertiesTable):

    def iterRows(self, **kwargs: Any) -> Iterator[XMLContent]:
        proc: UserDetails_GET.Processor = kwargs['proc']
        yield 'Role', proc.infoUser.uiRole

class OwnedJobsTable(JobsSubTable):
    widgetId = 'jobsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc: PageProcessor) -> Collection[Job]:
        return cast('UserDetails_GET.Processor', proc).jobs

class UserDetails_GET(FabPage['UserDetails_GET.Processor',
                              'UserDetails_GET.Arguments']):
    icon = 'IconUser'
    description = 'User Details'

    class Arguments(PageArgs):
        user = StrArg()

    class Processor(PageProcessor['UserDetails_GET.Arguments']):
        visibleJobs = 12
        userDB: ClassVar[UserDB]
        jobDB: ClassVar[JobDB]
        scheduleDB: ClassVar[ScheduleDB]

        async def process(self,
                          req: Request['UserDetails_GET.Arguments'],
                          user: User
                          ) -> None:
            infoUserName = req.args.user

            try:
                infoUser = self.userDB[infoUserName]
            except KeyError:
                raise PresentableError(xhtml[
                    'User ', xhtml.b[ infoUserName ], ' does not exist.'
                    ])

            jobDB = self.jobDB
            jobs = runQuery(
                [ ValueFilter('owner', infoUserName, jobDB),
                  KeySorter.forDB(['recent'], jobDB)
                  ],
                jobDB
                )[ : self.visibleJobs]

            # pylint: disable=attribute-defined-outside-init
            self.infoUser = infoUser
            self.jobs = jobs

    def checkAccess(self, user: User) -> None:
        pass

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        if proc.error is None:
            yield OwnedJobsTable.instance

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Any]]:
        if proc.error is None:
            yield OwnedJobsTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(UserDetails_GET.Processor, kwargs['proc'])
        infoUserName = proc.args.user
        requestUser = proc.user
        requestUserName = requestUser.name

        yield xhtml.h3[ 'Details of user ', xhtml.b[ infoUserName ], ':' ]
        yield DetailsTable.instance.present(**kwargs)

        if infoUserName == requestUserName:
            if requestUser.hasPrivilege('u/mo'):
                yield xhtml.p[
                    pageLink('ChangePassword')[ 'Change your password' ]
                    ]

        yield xhtml.h3[ 'Recent jobs:' ]
        yield OwnedJobsTable.instance.present(**kwargs)

        reportOwnerArgs = ReportArgs(owner={infoUserName})
        yield xhtml.p[
            pageLink('ReportIndex', reportOwnerArgs)[
                f'Show all jobs owned by {infoUserName}'
                ]
            ]
        yield xhtml.p[
            pageLink('ReportTasks', reportOwnerArgs)[
                f'Show tasks owned by {infoUserName}'
                ]
            ]

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield xhtml.p[ message ]

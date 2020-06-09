# SPDX-License-Identifier: BSD-3-Clause

from typing import Any, ClassVar, Iterable, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import DataTable
from softfab.joblib import Job, JobDB
from softfab.jobview import JobsSubTable
from softfab.pagelinks import JobIdSetArgs
from softfab.request import Request
from softfab.schedulelib import ScheduleDB
from softfab.userlib import User, UserDB, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import Widget, unorderedList
from softfab.xmlgen import XMLContent, xhtml


class ShowJobsTable(JobsSubTable):
    widgetId = 'jobsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc: PageProcessor) -> Iterable[Job]:
        assert isinstance(proc, ShowJobs_GET.Processor), proc
        return proc.jobs

class ShowJobs_GET(FabPage['ShowJobs_GET.Processor', 'ShowJobs_GET.Arguments']):
    icon = 'IconReport'
    description = 'Show Jobs'
    linkDescription = False

    class Arguments(JobIdSetArgs):
        pass

    class Processor(PageProcessor[JobIdSetArgs]):

        jobDB: ClassVar[JobDB]
        scheduleDB: ClassVar[ScheduleDB]
        userDB: ClassVar[UserDB]

        async def process(self, req: Request[JobIdSetArgs], user: User) -> None:
            jobs = []
            invalidJobIds = []
            jobDB = self.jobDB
            for jobId in req.args.jobId:
                try:
                    jobs.append(jobDB[jobId])
                except KeyError:
                    invalidJobIds.append(jobId)
            jobs.sort(key = jobDB.retrieverFor('recent'))
            invalidJobIds.sort()
            # pylint: disable=attribute-defined-outside-init
            self.jobs = jobs
            self.invalidJobIds = invalidJobIds

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/l')

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        yield ShowJobsTable.instance

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Any]]:
        yield ShowJobsTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ShowJobs_GET.Processor, kwargs['proc'])
        if len(proc.jobs) != 0:
            if proc.req.refererPage in ('BatchExecute', 'Execute',
                                        'FastExecute'):
                yield xhtml.p['Created the following ',
                              pluralize('job', len(proc.jobs)), ':']
            yield ShowJobsTable.instance.present(**kwargs)
        if len(proc.invalidJobIds) != 0:
            yield (
                xhtml.p[
                    'The following jobs ', xhtml.b[ 'do not exist' ], ': '
                    ],
                unorderedList[ proc.invalidJobIds ]
                )
        if len(proc.jobs) == 0 and len(proc.invalidJobIds) == 0:
            yield xhtml.p[ 'No job IDs specified.' ]

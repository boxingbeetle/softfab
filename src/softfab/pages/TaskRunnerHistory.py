# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Iterable, Iterator, List, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import DataTable
from softfab.joblib import Job, JobDB, Task
from softfab.pageargs import IntArg, SortArg
from softfab.pagelinks import TaskRunnerIdArgs
from softfab.querylib import runQuery
from softfab.request import Request
from softfab.tasktables import TaskRunsTable
from softfab.userlib import User, UserDB, checkPrivilege
from softfab.webgui import pageLink
from softfab.xmlgen import XMLContent, xhtml

# For large factories, sorting through all tasks that ever ran will take
# several minutes. The typical use case for Task Runner History is to see
# if task failures are linked to one particular Task Runner; in this scenario
# there is no need to go back far in time.
_jobsLimit = 10000

class HistoryTable(TaskRunsTable):

    def getRecordsToQuery(self, proc: PageProcessor) -> Iterable[Task]:
        proc = cast(TaskRunnerHistory_GET.Processor, proc)
        return proc.tasks

    def showTargetColumn(self, **kwargs: object) -> bool:
        # Typically a Task Runner has the same target for all of its life,
        # so this column is not useful.
        return False

class TaskRunnerHistory_GET(FabPage['TaskRunnerHistory_GET.Processor',
                                    'TaskRunnerHistory_GET.Arguments']):
    icon = 'TaskRunStat1'
    description = 'Task Runner History'

    class Arguments(TaskRunnerIdArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor['TaskRunnerHistory_GET.Arguments']):

        jobDB: ClassVar[JobDB]
        userDB: ClassVar[UserDB]

        async def process(self,
                          req: Request['TaskRunnerHistory_GET.Arguments'],
                          user: User
                          ) -> None:
            runnerId = req.args.runnerId

            jobDB = self.jobDB
            jobs = list(jobDB.values())
            jobs.sort(key = jobDB.retrieverFor('recent'))
            reachedJobsLimit = len(jobs) > _jobsLimit
            if reachedJobsLimit:
                jobs[_jobsLimit : ] = []

            # TODO: This is actually not a filter, since it changes the
            #       record type.
            def recordFilter(jobs: Iterable[Job]) -> List[Task]:
                return [
                    task
                    for job in jobs
                    for task in job.getTaskSequence()
                    if task['runner'] == runnerId
                    ]
            tasks = cast(List[Task], runQuery((recordFilter, ), jobs))

            # pylint: disable=attribute-defined-outside-init
            self.reachedJobsLimit = reachedJobsLimit
            self.tasks = tasks

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'r/l')
        checkPrivilege(user, 't/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield HistoryTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(TaskRunnerHistory_GET.Processor, kwargs['proc'])
        runnerId = proc.args.runnerId

        yield xhtml.h3[
            pageLink(
                'TaskRunnerDetails',
                TaskRunnerIdArgs.subset(proc.args)
                )[ 'Details' ],
            ' / History of Task Runner ', xhtml.b[ runnerId ], ':'
            ]

        if proc.reachedJobsLimit:
            yield xhtml.p[xhtml.i[
                f'Only tasks from the last {_jobsLimit:d} jobs are shown.'
                ]]
        yield HistoryTable.instance.present(**kwargs)

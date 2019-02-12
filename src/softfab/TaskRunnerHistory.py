# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.joblib import jobDB
from softfab.pageargs import IntArg, SortArg
from softfab.pagelinks import TaskRunnerIdArgs
from softfab.querylib import runQuery
from softfab.taskrunnerlib import taskRunnerDB
from softfab.tasktables import TaskRunsTable
from softfab.webgui import pageLink
from softfab.xmlgen import xhtml

# For large factories, sorting through all tasks that ever ran will take
# several minutes. The typical use case for Task Runner History is to see
# if task failures are linked to one particular Task Runner; in this scenario
# there is no need to go back far in time.
_jobsLimit = 10000

class HistoryTable(TaskRunsTable):

    def getRecordsToQuery(self, proc):
        return proc.tasks

    def showTargetColumn(self):
        # Typically a Task Runner has the same target for all of its life,
        # so this column is not useful.
        return False

class TaskRunnerHistory(FabPage):
    icon = 'TaskRunStat1'
    description = 'Task Runner History'

    class Arguments(TaskRunnerIdArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):

        def process(self, req):
            runnerId = req.args.runnerId

            taskRunner = taskRunnerDB.get(runnerId)

            jobs = list(jobDB.values())
            jobs.sort(key = jobDB.retrieverFor('recent'))
            reachedJobsLimit = len(jobs) > _jobsLimit
            if reachedJobsLimit:
                jobs[_jobsLimit : ] = []

            def recordFilter(jobs):
                return [
                    task
                    for job in jobs
                    for task in job.getTaskSequence()
                    if task['runner'] == runnerId
                    ]
            tasks = runQuery((recordFilter, ), jobs)

            # pylint: disable=attribute-defined-outside-init
            self.taskRunner = taskRunner
            self.reachedJobsLimit = reachedJobsLimit
            self.tasks = tasks

    def checkAccess(self, req):
        req.checkPrivilege('tr/a')
        req.checkPrivilege('t/l')

    def iterDataTables(self, proc):
        yield HistoryTable.instance

    def presentContent(self, proc):
        runnerId = proc.args.runnerId

        if proc.taskRunner is None:
            yield xhtml.p[
                xhtml.b[ 'Note:' ], ' Task Runner ', xhtml.b[ runnerId ],
                ' does not exist (anymore).'
                ]
        else:
            yield xhtml.h2[
                pageLink(
                    'TaskRunnerDetails',
                    TaskRunnerIdArgs.subset(proc.args)
                    )[ 'Details' ],
                ' / History of ', xhtml.b[ runnerId ], ':'
                ]

        if proc.reachedJobsLimit:
            yield xhtml.p[xhtml.i[
                'Only tasks from the last %d jobs are shown.' % _jobsLimit
                ]]
        yield HistoryTable.instance.present(proc=proc)

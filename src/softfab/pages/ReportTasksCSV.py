# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, List, Sequence

from softfab.CSVPage import CSVPage
from softfab.ReportMixin import ReportProcessor
from softfab.joblib import iterDoneTasks
from softfab.pagelinks import ReportTaskCSVArgs
from softfab.querylib import KeySorter, RecordProcessor, runQuery
from softfab.request import Request
from softfab.setcalc import union
from softfab.taskrunlib import getData, getKeys
from softfab.taskview import getTaskStatus
from softfab.timeview import formatTime
from softfab.userlib import User, checkPrivilege


class ReportTasksCSV_GET(CSVPage['ReportTasksCSV_GET.Processor']):

    class Arguments(ReportTaskCSVArgs):
        pass

    class Processor(ReportProcessor[Arguments]):

        def process(self,
                    req: Request['ReportTasksCSV_GET.Arguments'],
                    user: User
                    ) -> None:
            super().process(req, user)

            # Note: iterDoneTasks() can efficiently handle an empty (nothing
            #       matches) filter, no need for a special case here.
            query: List[RecordProcessor] = list(self.iterFilters())
            query.append(KeySorter.forCustom(['recent']))
            tasks = runQuery(query, iterDoneTasks(self.args.task))

            # pylint: disable=attribute-defined-outside-init
            self.tasks = tasks

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/a', 'view the task list')

    def getFileName(self, proc: Processor) -> str:
        return '_'.join(['export'] + sorted(proc.args.task)) + '.csv'

    def iterRows(self, proc: Processor) -> Iterator[Sequence[str]]:
        tasks = proc.tasks

        # Determine all keys that exist for the given task names.
        keys = sorted(union(
            getKeys(taskName) for taskName in proc.args.task
            ))

        yield [ 'create date', 'create time', 'result' ] + keys
        for task in tasks:
            taskName = task.getName()
            taskKeys = getKeys(taskName)
            # TODO: Which properties are useful to export?
            timestamp = formatTime(task.getJob().getCreateTime())
            # Assuming format "2008-09-16 15:21"
            results = [timestamp[:10], timestamp[-5:], getTaskStatus(task)]
            for key in keys:
                if key in taskKeys:
                    # TODO: Querying one run at a time is not really efficient.
                    data = list(getData(
                        taskName, [ task.getLatestRun().getId() ], key
                        ))
                    if len(data) == 0:
                        results.append('')
                    else:
                        assert len(data) == 1
                        value = data[0][1]
                        results.append(str(value))
                else:
                    results.append('')
            yield results

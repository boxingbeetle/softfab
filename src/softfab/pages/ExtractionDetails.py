# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError
from softfab.ReportMixin import ReportTaskArgs
from softfab.joblib import jobDB
from softfab.pagelinks import TaskIdArgs
from softfab.resultlib import getData, getKeys
from softfab.userlib import checkPrivilege
from softfab.webgui import Table, cell, pageLink
from softfab.xmlgen import XMLContent, xhtml


class ExtractionDetails_GET(FabPage['ExtractionDetails_GET.Processor', 'ExtractionDetails_GET.Arguments']):
    icon = 'IconReport'
    description = 'Extracted Data'

    class Arguments(TaskIdArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            # pylint: disable=attribute-defined-outside-init
            try:
                job = jobDB[req.args.jobId]
            except KeyError:
                raise PresentableError(xhtml.p[
                    'There is no job with ID ', xhtml.b[ req.args.jobId ], '.'
                    ])
            task = job.getTask(req.args.taskName)
            if task is None:
                raise PresentableError(xhtml.p[
                    'There is task named ', xhtml.b[ req.args.taskName ],
                    ' in job ', xhtml.b[ req.args.jobId ], '.'
                    ])
            self.task = task

    def checkAccess(self, req):
        checkPrivilege(req.user, 't/a')

    def presentContent(self, proc: Processor) -> XMLContent:
        taskName = proc.task.getName()
        yield xhtml.p[ 'Extracted data for task ', xhtml.b[ taskName ], ':' ]
        yield DetailsTable.instance.present(proc=proc)
        yield xhtml.p[
            pageLink('ExtractedData', ReportTaskArgs(task = ( taskName, )))[
                'Visualize trends of ', xhtml.b[ taskName ]
                ]
            ]

class DetailsTable(Table):
    columns = 'Key', 'Value'

    def iterRows(self, *, proc, **kwargs):
        taskRun = proc.task.getLatestRun()
        taskRunId = taskRun.getId()
        taskName = taskRun.getName()
        for key in sorted(getKeys(taskName)):
            values = []
            for run, value in getData(taskName, [ taskRunId ], key):
                assert run == taskRunId
                values.append(value)
            if len(values) == 0:
                value = '-'
            else:
                assert len(values) == 1
                value = values[0]
            yield key, cell(class_ = 'rightalign')[value]

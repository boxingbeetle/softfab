# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import PageProcessor, PresentableError
from softfab.RecordDelete import RecordDelete_GET, RecordDelete_POSTMixin
from softfab.connection import ConnectionStatus
from softfab.pageargs import RefererArg
from softfab.taskrunnerlib import taskRunnerDB
from softfab.xmlgen import xhtml


class DelTaskRunnerRecord_GET(RecordDelete_GET):
    db = taskRunnerDB
    recordName = 'record of Task Runner'
    denyText = 'Task Runners'

    description = 'Delete Task Runner Record'
    icon = 'IconResources'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('ResourceIndex')
        detailsQuery = RefererArg('TaskRunnerDetails')

    def checkState(self, record):
        if record.getConnectionStatus() is not ConnectionStatus.LOST:
            raise PresentableError(xhtml.p[
                'Cannot delete record of Task Runner ',
                xhtml.b[ record.getId() ], ': '
                'it is not lost (anymore).'
                ])

class DelTaskRunnerRecord_POST(RecordDelete_POSTMixin, DelTaskRunnerRecord_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    RecordDelete_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    PageProcessor['DelTaskRunnerRecord_POST.Arguments']):
        pass

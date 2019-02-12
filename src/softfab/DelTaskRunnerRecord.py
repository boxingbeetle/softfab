# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import PresentableError
from softfab.RecordDelete import RecordDelete_GET, RecordDelete_POSTMixin
from softfab.connection import ConnectionStatus
from softfab.pageargs import RefererArg
from softfab.taskrunnerlib import taskRunnerDB
from softfab.xmlgen import xhtml

class ParentArgs:
    indexQuery = RefererArg('ResourceIndex')
    detailsQuery = RefererArg('TaskRunnerDetails')

class DelTaskRunnerRecord_GET(RecordDelete_GET):
    db = taskRunnerDB
    recordName = 'record of Task Runner'
    denyText = 'Task Runners'

    description = 'Delete Task Runner Record'
    icon = 'IconResources'

    class Arguments(RecordDelete_GET.Arguments, ParentArgs):
        pass

    def checkState(self, record):
        if record.getConnectionStatus() is not ConnectionStatus.LOST:
            raise PresentableError(xhtml.p[
                'Cannot delete record of Task Runner ',
                xhtml.b[ record.getId() ], ': '
                'it is not lost (anymore).'
                ])

class DelTaskRunnerRecord_POST(RecordDelete_POSTMixin, DelTaskRunnerRecord_GET):

    class Arguments(RecordDelete_POSTMixin.Arguments, ParentArgs):
        pass

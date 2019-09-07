# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import PageProcessor
from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
)
from softfab.frameworklib import Framework, frameworkDB
from softfab.frameworkview import taskDefsUsingFramework
from softfab.pageargs import RefererArg
from softfab.pagelinks import createTaskDetailsLink


class FrameworkDelete_GET(RecordDelete_GET):
    db = frameworkDB
    recordName = 'framework'
    denyText = 'framework definitions'

    description = 'Delete Framework'
    icon = 'Framework1'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('FrameworkIndex')
        detailsQuery = RefererArg('FrameworkDetails')

    def checkState(self, record: Framework) -> None:
        taskDefs = list(taskDefsUsingFramework(record.getId()))
        if taskDefs:
            raise RecordInUseError(
                'task definition', createTaskDetailsLink, taskDefs
                )

class FrameworkDelete_POST(RecordDelete_POSTMixin, FrameworkDelete_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    FrameworkDelete_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    PageProcessor['FrameworkDelete_POST.Arguments']):
        pass

# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar

from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
)
from softfab.frameworklib import Framework, FrameworkDB
from softfab.frameworkview import taskDefsUsingFramework
from softfab.pageargs import RefererArg
from softfab.pagelinks import createTaskDetailsLink
from softfab.taskdeflib import TaskDefDB


class FrameworkDelete_GET(RecordDelete_GET):
    description = 'Delete Framework'
    icon = 'Framework1'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('FrameworkIndex')
        detailsQuery = RefererArg('FrameworkDetails')

    class Processor(RecordDelete_GET.Processor[Framework]):
        frameworkDB: ClassVar[FrameworkDB]
        taskDefDB: ClassVar[TaskDefDB]
        recordName = 'framework'
        denyText = 'framework definitions'

        @property
        def db(self) -> FrameworkDB:
            return self.frameworkDB

        def checkState(self, record: Framework) -> None:
            taskDefs = list(
                taskDefsUsingFramework(self.taskDefDB, record.getId())
                )
            if taskDefs:
                raise RecordInUseError(
                    'task definition', createTaskDetailsLink, taskDefs
                    )

class FrameworkDelete_POST(RecordDelete_POSTMixin, FrameworkDelete_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    FrameworkDelete_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    FrameworkDelete_GET.Processor):
        pass

# SPDX-License-Identifier: BSD-3-Clause

from functools import partial
from typing import ClassVar

from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
)
from softfab.configlib import ConfigDB
from softfab.pageargs import RefererArg
from softfab.pagelinks import createConfigDetailsLink
from softfab.taskdeflib import TaskDef, TaskDefDB
from softfab.taskdefview import configsUsingTaskDef


class ParentArgs:
    indexQuery = RefererArg('TaskIndex')
    detailsQuery = RefererArg('TaskDetails')

class TaskDelete_GET(RecordDelete_GET):
    description = 'Delete Task Definition'
    icon = 'TaskDef2'

    class Arguments(RecordDelete_GET.Arguments, ParentArgs):
        pass

    class Processor(RecordDelete_GET.Processor[TaskDef]):
        configDB: ClassVar[ConfigDB]
        taskDefDB: ClassVar[TaskDefDB]
        recordName = 'task definition'
        denyText = 'task definitions'

        @property
        def db(self) -> TaskDefDB:
            return self.taskDefDB

        def checkState(self, record: TaskDef) -> None:
            configDB = self.configDB
            configs = list(configsUsingTaskDef(configDB, record.getId()))
            if configs:
                raise RecordInUseError(
                    'configuration',
                    partial(createConfigDetailsLink, configDB),
                    configs
                    )

class TaskDelete_POST(RecordDelete_POSTMixin, TaskDelete_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    TaskDelete_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    TaskDelete_GET.Processor):
        pass

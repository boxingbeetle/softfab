# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import PageProcessor
from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
)
from softfab.pageargs import RefererArg
from softfab.pagelinks import createConfigDetailsLink
from softfab.taskdeflib import TaskDef, taskDefDB
from softfab.taskdefview import configsUsingTaskDef


class ParentArgs:
    indexQuery = RefererArg('TaskIndex')
    detailsQuery = RefererArg('TaskDetails')

class TaskDelete_GET(RecordDelete_GET):
    db = taskDefDB
    recordName = 'task definition'
    denyText = 'task definitions'

    description = 'Delete Task Definition'
    icon = 'TaskDef2'

    class Arguments(RecordDelete_GET.Arguments, ParentArgs):
        pass

    def checkState(self, record: TaskDef) -> None:
        configs = list(configsUsingTaskDef(record.getId()))
        if configs:
            raise RecordInUseError(
                'configuration', createConfigDetailsLink, configs
                )

class TaskDelete_POST(RecordDelete_POSTMixin, TaskDelete_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    TaskDelete_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    PageProcessor['TaskDelete_POST.Arguments']):
        pass

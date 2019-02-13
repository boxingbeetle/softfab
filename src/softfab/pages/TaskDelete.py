# SPDX-License-Identifier: BSD-3-Clause

from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
    )
from softfab.pageargs import RefererArg
from softfab.pagelinks import createConfigDetailsLink
from softfab.taskdeflib import taskDefDB
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

    def checkState(self, record):
        configs = list(configsUsingTaskDef(record.getId()))
        if configs:
            raise RecordInUseError(
                'configuration', createConfigDetailsLink, configs
                )

class TaskDelete_POST(RecordDelete_POSTMixin, TaskDelete_GET):

    class Arguments(RecordDelete_POSTMixin.Arguments, ParentArgs):
        pass

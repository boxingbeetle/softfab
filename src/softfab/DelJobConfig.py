# SPDX-License-Identifier: BSD-3-Clause

from RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
    )
from configlib import configDB
from configview import schedulesUsingConfig
from pageargs import RefererArg
from schedulerefs import createScheduleDetailsLink

class ParentArgs:
    detailsQuery = RefererArg('ConfigDetails')
    indexQuery = RefererArg('LoadExecute')

class DelJobConfig_GET(RecordDelete_GET):
    db = configDB
    recordName = 'configuration'
    denyText = 'configurations'

    description = 'Delete Configuration'
    icon = 'IconExec'

    class Arguments(RecordDelete_GET.Arguments, ParentArgs):
        pass

    def checkState(self, record):
        schedules = list(schedulesUsingConfig(record.getId()))
        if schedules:
            raise RecordInUseError(
                'schedule', createScheduleDetailsLink, schedules
                )

class DelJobConfig_POST(RecordDelete_POSTMixin, DelJobConfig_GET):

    class Arguments(RecordDelete_POSTMixin.Arguments, ParentArgs):
        pass

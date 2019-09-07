# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import PageProcessor
from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
)
from softfab.configlib import Config, configDB
from softfab.configview import schedulesUsingConfig
from softfab.pageargs import RefererArg
from softfab.schedulerefs import createScheduleDetailsLink


class DelJobConfig_GET(RecordDelete_GET):
    db = configDB
    recordName = 'configuration'
    denyText = 'configurations'

    description = 'Delete Configuration'
    icon = 'IconExec'

    class Arguments(RecordDelete_GET.Arguments):
        detailsQuery = RefererArg('ConfigDetails')
        indexQuery = RefererArg('LoadExecute')

    def checkState(self, record: Config) -> None:
        schedules = list(schedulesUsingConfig(record.getId()))
        if schedules:
            raise RecordInUseError(
                'schedule', createScheduleDetailsLink, schedules
                )

class DelJobConfig_POST(RecordDelete_POSTMixin, DelJobConfig_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    DelJobConfig_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    PageProcessor['DelJobConfig_POST.Arguments']):
        pass

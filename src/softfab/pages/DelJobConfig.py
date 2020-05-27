# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar

from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
)
from softfab.configlib import Config, ConfigDB
from softfab.configview import schedulesUsingConfig
from softfab.pageargs import RefererArg
from softfab.schedulelib import ScheduleDB
from softfab.schedulerefs import createScheduleDetailsLink


class DelJobConfig_GET(RecordDelete_GET):
    description = 'Delete Configuration'
    icon = 'IconExec'

    class Arguments(RecordDelete_GET.Arguments):
        detailsQuery = RefererArg('ConfigDetails')
        indexQuery = RefererArg('LoadExecute')

    class Processor(RecordDelete_GET.Processor[Config]):
        configDB: ClassVar[ConfigDB]
        scheduleDB: ClassVar[ScheduleDB]
        recordName = 'configuration'
        denyText = 'configurations'

        @property
        def db(self) -> ConfigDB:
            return self.configDB

        def checkState(self, record: Config) -> None:
            schedules = list(
                schedulesUsingConfig(self.scheduleDB, record.getId())
                )
            if schedules:
                raise RecordInUseError(
                    'schedule', createScheduleDetailsLink, schedules
                    )

class DelJobConfig_POST(RecordDelete_POSTMixin, DelJobConfig_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    DelJobConfig_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    DelJobConfig_GET.Processor):
        pass

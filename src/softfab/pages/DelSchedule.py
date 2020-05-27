# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar

from softfab.RecordDelete import RecordDelete_GET, RecordDelete_POSTMixin
from softfab.pageargs import RefererArg
from softfab.schedulelib import ScheduleDB, Scheduled


class DelSchedule_GET(RecordDelete_GET):
    description = 'Delete Schedule'
    icon = 'IconSchedule'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('ScheduleIndex')
        detailsQuery = RefererArg('ScheduleDetails')

    class Processor(RecordDelete_GET.Processor[Scheduled]):
        scheduleDB: ClassVar[ScheduleDB]
        recordName = 'schedule'
        denyText = 'schedules'

        @property
        def db(self) -> ScheduleDB:
            return self.scheduleDB

class DelSchedule_POST(RecordDelete_POSTMixin, DelSchedule_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    DelSchedule_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    DelSchedule_GET.Processor):
        pass

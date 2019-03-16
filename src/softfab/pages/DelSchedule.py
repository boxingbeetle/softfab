# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import PageProcessor
from softfab.RecordDelete import RecordDelete_GET, RecordDelete_POSTMixin
from softfab.pageargs import RefererArg
from softfab.schedulelib import scheduleDB


class DelSchedule_GET(RecordDelete_GET):
    db = scheduleDB
    recordName = 'schedule'
    denyText = 'schedules'

    description = 'Delete Schedule'
    icon = 'IconSchedule'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('ScheduleIndex')
        detailsQuery = RefererArg('ScheduleDetails')

class DelSchedule_POST(RecordDelete_POSTMixin, DelSchedule_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    DelSchedule_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin, PageProcessor):
        pass

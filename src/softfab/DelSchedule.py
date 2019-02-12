# SPDX-License-Identifier: BSD-3-Clause

from softfab.RecordDelete import RecordDelete_GET, RecordDelete_POSTMixin
from softfab.pageargs import RefererArg
from softfab.schedulelib import scheduleDB

class ParentArgs:
    indexQuery = RefererArg('ScheduleIndex')
    detailsQuery = RefererArg('ScheduleDetails')

class DelSchedule_GET(RecordDelete_GET):
    db = scheduleDB
    recordName = 'schedule'
    denyText = 'schedules'

    description = 'Delete Schedule'
    icon = 'IconSchedule'

    class Arguments(RecordDelete_GET.Arguments, ParentArgs):
        pass

class DelSchedule_POST(RecordDelete_POSTMixin, DelSchedule_GET):

    class Arguments(RecordDelete_POSTMixin.Arguments, ParentArgs):
        pass

# SPDX-License-Identifier: BSD-3-Clause

from typing import Any, ClassVar, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.ReportMixin import JobReportProcessor, ReportFilterForm
from softfab.datawidgets import DataTable
from softfab.formlib import textInput
from softfab.joblib import JobDB
from softfab.jobview import JobsTable
from softfab.pageargs import IntArg, SortArg, StrArg
from softfab.pagelinks import ReportArgs
from softfab.querylib import RecordFilter, WildcardFilter
from softfab.schedulelib import ScheduleDB
from softfab.users import User, checkPrivilege
from softfab.xmlgen import XMLContent, xhtml


class FilteredJobsTable(JobsTable):

    def showTargetColumn(self, **kwargs: object) -> bool:
        jobDB: JobDB = getattr(kwargs['proc'], 'jobDB')
        return super().showTargetColumn(**kwargs) \
            or bool(jobDB.uniqueValues('target'))

    def iterFilters(self, proc: PageProcessor) -> Iterator[RecordFilter]:
        return cast(ReportIndex_GET.Processor, proc).iterFilters()

class FilterForm(ReportFilterForm):
    objectName = FilteredJobsTable.objectName

    def presentCustomBox(self, **kwargs: object) -> XMLContent:
        proc = cast(ReportIndex_GET.Processor, kwargs['proc'])
        yield xhtml.td[ 'Description:' ]
        yield xhtml.td(colspan = 3)[
            textInput(
                name='desc', value=proc.args.desc,
                style='width:100%'
                )
            ]

class ReportIndex_GET(FabPage['ReportIndex_GET.Processor',
                              'ReportIndex_GET.Arguments']):
    icon = 'IconReport'
    description = 'History'
    children = ['ShowReport', 'ShowJobs', 'ReportTasks', 'TaskMatrix']

    class Arguments(ReportArgs):
        first = IntArg(0)
        sort = SortArg()
        desc = StrArg(None)

    class Processor(JobReportProcessor[Arguments]):

        jobDB: ClassVar[JobDB]
        scheduleDB: ClassVar[ScheduleDB]

        def iterFilters(self) -> Iterator[RecordFilter]:
            yield from super().iterFilters()
            if self.args.desc:
                yield WildcardFilter('description', self.args.desc, self.db)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/l', 'view the report list')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Any]]:
        yield FilteredJobsTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield FilterForm.instance.present(numListItems=5, **kwargs)
        yield FilteredJobsTable.instance.present(**kwargs)

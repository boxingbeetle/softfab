# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.ReportMixin import (
    JobReportProcessor, ReportArgs, ReportFilterForm
)
from softfab.datawidgets import DataTable
from softfab.formlib import textInput
from softfab.joblib import jobDB
from softfab.jobview import JobsTable
from softfab.pageargs import IntArg, SortArg, StrArg
from softfab.querylib import WildcardFilter
from softfab.userlib import checkPrivilege
from softfab.xmlgen import XMLContent, xhtml


class FilteredJobsTable(JobsTable):

    def showTargetColumn(self):
        return super().showTargetColumn() \
            or len(jobDB.uniqueValues('target')) > 1

    def iterFilters(self, proc):
        return proc.iterFilters()

class FilterForm(ReportFilterForm):
    objectName = FilteredJobsTable.objectName

    def presentCustomBox(self, proc, **kwargs):
        yield xhtml.td[ 'Description:' ]
        yield xhtml.td(colspan = 3)[
            textInput(
                name='desc', value=proc.args.desc,
                style='width:100%'
                )
            ]

class ReportIndex_GET(FabPage['ReportIndex_GET.Processor', 'ReportIndex_GET.Arguments']):
    icon = 'IconReport'
    description = 'History'
    children = [
        'ShowReport', 'ShowJobs', 'ReportTasks', 'TaskMatrix', 'StorageIndex',
        'ShadowQueue'
        ]

    class Arguments(ReportArgs):
        first = IntArg(0)
        sort = SortArg()
        desc = StrArg(None)

    class Processor(JobReportProcessor):

        def iterFilters(self):
            yield from super().iterFilters()
            if self.args.desc:
                yield WildcardFilter('description', self.args.desc, self.db)

    def checkAccess(self, req):
        checkPrivilege(req.user, 'j/l', 'view the report list')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield FilteredJobsTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
        yield FilterForm.instance.present(proc=proc, numListItems=5)
        yield FilteredJobsTable.instance.present(proc=proc)

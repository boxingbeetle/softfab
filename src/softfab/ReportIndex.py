# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from ReportMixin import JobReportProcessor, ReportArgs, ReportFilterForm
from formlib import textInput
from joblib import jobDB
from jobview import JobsTable
from pageargs import IntArg, SortArg, StrArg
from querylib import WildcardFilter
from xmlgen import xhtml

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

class ReportIndex(FabPage):
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
            yield from JobReportProcessor.iterFilters(self)
            if self.args.desc:
                yield WildcardFilter('description', self.args.desc, self.db)

    def checkAccess(self, req):
        req.checkPrivilege('j/l', 'view the report list')

    def iterDataTables(self, proc):
        yield FilteredJobsTable.instance

    def presentContent(self, proc):
        yield FilterForm.instance.present(proc=proc, numListItems=5)
        yield FilteredJobsTable.instance.present(proc=proc)

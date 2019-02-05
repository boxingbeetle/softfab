# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from Page import PageProcessor
from joblib import jobDB
from jobview import JobsSubTable
from pagelinks import JobIdSetArgs
from webgui import unorderedList
from xmlgen import xhtml

class ShowJobsTable(JobsSubTable):
    widgetId = 'jobsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc):
        return proc.jobs

class ShowJobs(FabPage):
    icon = 'IconReport'
    description = 'Show Jobs'
    linkDescription = False

    class Arguments(JobIdSetArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            jobs = []
            invalidJobIds = []
            for jobId in req.args.jobId:
                try:
                    jobs.append(jobDB[jobId])
                except KeyError:
                    invalidJobIds.append(jobId)
            jobs.sort(key = jobDB.retrieverFor('recent'))
            invalidJobIds.sort()
            # pylint: disable=attribute-defined-outside-init
            self.jobs = jobs
            self.invalidJobIds = invalidJobIds

    def checkAccess(self, req):
        req.checkPrivilege('j/l')

    def iterWidgets(self, proc):
        yield ShowJobsTable

    def iterDataTables(self, proc):
        yield ShowJobsTable.instance

    def presentContent(self, proc):
        if len(proc.jobs) != 0:
            if proc.req.refererPage in (
                'BatchExecute', 'Execute', 'FastExecute'
                ):
                yield xhtml.p[
                    'Created the following %s:'
                    % ( 'jobs', 'job' )[ len(proc.jobs) == 1 ]
                    ]
            yield ShowJobsTable.instance.present(proc=proc)
        if len(proc.invalidJobIds) != 0:
            yield (
                xhtml.p[
                    'The following jobs ', xhtml.b[ 'do not exist' ], ': '
                    ],
                unorderedList[ proc.invalidJobIds ]
                )
        if len(proc.jobs) == 0 and len(proc.invalidJobIds) == 0:
            yield xhtml.p[ 'No job IDs specified.' ]

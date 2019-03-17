# SPDX-License-Identifier: BSD-3-Clause

from twisted.internet.defer import inlineCallbacks

from softfab.ControlPage import ControlPage
from softfab.ReportMixin import JobReportProcessor, ReportArgs
from softfab.joblib import jobDB
from softfab.pageargs import SetArg
from softfab.querylib import SetFilter, runQuery
from softfab.userlib import IUser, checkPrivilege
from softfab.utils import chop
from softfab.xmlgen import adaptToXML, xml


class GetJobHistory_GET(ControlPage['GetJobHistory_GET.Arguments', 'GetJobHistory_GET.Processor']):

    class Arguments(ReportArgs):
        configId = SetArg()

    def checkAccess(self, user: IUser) -> None:
        checkPrivilege(user, 'j/l', 'view the report list')

    class Processor(JobReportProcessor):

        def process(self, req):
            super().process(req)

            jobs = runQuery(self.iterFilters(), jobDB)

            # pylint: disable=attribute-defined-outside-init
            self.jobs = jobs

        def iterFilters(self):
            yield from super().iterFilters()

            configId = self.args.configId
            if configId:
                yield SetFilter('configId', configId, jobDB)

    @inlineCallbacks
    def writeReply(self, response, proc):
        jobs = proc.jobs
        response.write('<jobrefs>')
        for chunk in chop(jobs, 1000):
            # Measurements have shown that a single write with a big XML
            # sequence is much faster than many small writes.
            response.write(adaptToXML(
                xml.jobref(jobid = job.getId())
                for job in chunk
                ))
            # Return control to reactor.
            yield response.returnToReactor()
        response.write('</jobrefs>')

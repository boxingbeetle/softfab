# SPDX-License-Identifier: BSD-3-Clause

from ControlPage import ControlPage
from ReportMixin import ReportArgs, JobReportProcessor
from joblib import jobDB
from pageargs import SetArg
from querylib import SetFilter, runQuery
from utils import chop
from xmlgen import adaptToXML, xml

from twisted.internet import defer

class GetJobHistory(ControlPage):

    class Arguments(ReportArgs):
        configId = SetArg()

    def checkAccess(self, req):
        req.checkPrivilege('j/l', 'view the report list')

    class Processor(JobReportProcessor):

        def process(self, req):
            JobReportProcessor.process(self, req)

            jobs = runQuery(self.iterFilters(), jobDB)

            # pylint: disable=attribute-defined-outside-init
            self.jobs = jobs

        def iterFilters(self):
            yield from JobReportProcessor.iterFilters(self)

            configId = self.args.configId
            if configId:
                yield SetFilter('configId', configId, jobDB)

    @defer.inlineCallbacks
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

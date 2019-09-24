# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from twisted.internet.defer import Deferred, inlineCallbacks

from softfab.ControlPage import ControlPage
from softfab.ReportMixin import JobReportProcessor, ReportArgs
from softfab.joblib import jobDB
from softfab.pageargs import SetArg
from softfab.querylib import RecordFilter, SetFilter, runQuery
from softfab.request import Request
from softfab.response import Response
from softfab.userlib import User, checkPrivilege
from softfab.utils import chop
from softfab.xmlgen import xml


class GetJobHistory_GET(ControlPage['GetJobHistory_GET.Arguments',
                                    'GetJobHistory_GET.Processor']):

    class Arguments(ReportArgs):
        configId = SetArg()

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/l', 'view the report list')

    class Processor(JobReportProcessor[Arguments]):

        def process(self,
                    req: Request['GetJobHistory_GET.Arguments'],
                    user: User
                    ) -> None:
            super().process(req, user)

            jobs = runQuery(self.iterFilters(), jobDB)

            # pylint: disable=attribute-defined-outside-init
            self.jobs = jobs

        def iterFilters(self) -> Iterator[RecordFilter]:
            yield from super().iterFilters()

            configId = self.args.configId
            if configId:
                yield SetFilter('configId', configId, jobDB)

    @inlineCallbacks
    def writeReply(self,
                   response: Response,
                   proc: Processor
                   ) -> Iterator[Deferred]:
        jobs = proc.jobs
        response.write('<jobrefs>')
        for chunk in chop(jobs, 1000):
            # Measurements have shown that a single write with a big XML
            # sequence is much faster than many small writes.
            response.writeXML(
                xml.jobref(jobid = job.getId())
                for job in chunk
                )
            # Return control to reactor.
            yield response.returnToReactor()
        response.write('</jobrefs>')

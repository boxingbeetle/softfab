# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Iterator

from softfab.ControlPage import ControlPage
from softfab.ReportMixin import JobReportProcessor
from softfab.joblib import JobDB
from softfab.pageargs import SetArg
from softfab.pagelinks import ReportArgs
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

        jobDB: ClassVar[JobDB]

        async def process(self,
                          req: Request['GetJobHistory_GET.Arguments'],
                          user: User
                          ) -> None:
            await super().process(req, user)

            jobs = runQuery(self.iterFilters(), self.jobDB)

            # pylint: disable=attribute-defined-outside-init
            self.jobs = jobs

        def iterFilters(self) -> Iterator[RecordFilter]:
            yield from super().iterFilters()

            configId = self.args.configId
            if configId:
                yield SetFilter('configId', configId, self.jobDB)

    async def writeReply(self, response: Response, proc: Processor) -> None:
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
            await response.returnToReactor()
        response.write('</jobrefs>')

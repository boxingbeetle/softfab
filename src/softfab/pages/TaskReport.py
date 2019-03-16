# SPDX-License-Identifier: BSD-3-Clause

from urllib.parse import urlsplit

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.authentication import NoAuthPage
from softfab.joblib import jobDB
from softfab.pageargs import PageArgs, StrArg
from softfab.shadowlib import shadowDB
from softfab.xmlgen import xml


class TaskReport_POST(ControlPage['TaskReport_POST.Arguments', 'TaskReport_POST.Processor']):
    authenticator = NoAuthPage

    class Arguments(PageArgs):
        id = StrArg(None)
        name = StrArg(None)
        shadowId = StrArg(None)
        url = StrArg()

    class Processor(PageProcessor):

        def process(self, req):
            jobId = req.args.id
            taskName = req.args.name
            shadowId = req.args.shadowId
            url = req.args.url

            if jobId is None and shadowId is None:
                raise InvalidRequest('Neither "id" nor "shadowId" was supplied')
            if jobId is not None and shadowId is not None:
                raise InvalidRequest('Both "id" and "shadowId" were supplied')
            if shadowId is None:
                try:
                    job = jobDB[jobId]
                except KeyError:
                    raise InvalidRequest('Job "%s" does not exist' % jobId)
                run = job.getTask(taskName)
                if run is None:
                    raise InvalidRequest(
                        'Job "%s" does not contain task "%s"'
                        % ( jobId, taskName )
                        )
            else:
                try:
                    run = shadowDB[shadowId]
                except KeyError:
                    raise InvalidRequest(
                        'Shadow run "%s" does not exist' % shadowId
                        )

            parts = urlsplit(url)
            if parts[0] not in ('http', 'https') or parts[1] == '':
                raise InvalidRequest(
                    'URL "%s" is not an absolute HTTP(S) URL' % url
                    )
            run.setURL(url)

    def checkAccess(self, user):
        pass

    def writeReply(self, response, proc):
        response.write(xml.ok)

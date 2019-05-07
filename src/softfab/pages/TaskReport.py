# SPDX-License-Identifier: BSD-3-Clause

from urllib.parse import urlsplit

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.authentication import TokenAuthPage
from softfab.joblib import jobDB
from softfab.pageargs import PageArgs, StrArg
from softfab.resourcelib import runnerFromToken
from softfab.response import Response
from softfab.shadowlib import shadowDB
from softfab.tokens import TokenRole, TokenUser
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml


class TaskReport_POST(ControlPage['TaskReport_POST.Arguments',
                                  'TaskReport_POST.Processor']):
    authenticator = TokenAuthPage(TokenRole.RESOURCE)

    class Arguments(PageArgs):
        id = StrArg(None)
        name = StrArg(None)
        shadowId = StrArg(None)
        url = StrArg()

    class Processor(PageProcessor['TaskReport_POST.Arguments']):

        def process(self, req, user):
            jobId = req.args.id
            taskName = req.args.name
            shadowId = req.args.shadowId
            url = req.args.url

            # Find Task Runner.
            assert isinstance(user, TokenUser), user
            try:
                taskRunner = runnerFromToken(user)
            except KeyError as ex:
                raise InvalidRequest(*ex.args) from ex

            if jobId is None and shadowId is None:
                raise InvalidRequest('Neither "id" nor "shadowId" was supplied')
            if jobId is not None and shadowId is not None:
                raise InvalidRequest('Both "id" and "shadowId" were supplied')
            if shadowId is None:
                runningTask = taskRunner.getRun()
                if runningTask is None:
                    raise InvalidRequest(
                        'Task Runner "%s" is not running a task'
                        % taskRunner.getId()
                        )
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
                runId = run['run']
                if runningTask.getId() != runId:
                    raise InvalidRequest(
                        'Task Runner "%s" is running task %s '
                        'but wants to set report for %s'
                        % (taskRunner.getId(), runningTask.getId(), runId)
                        )
            else:
                runningShadowId = taskRunner.getShadowRunId()
                if runningShadowId is None:
                    raise InvalidRequest(
                        'Task Runner "%s" is not running a shadow task'
                        % taskRunner.getId()
                        )
                elif runningShadowId != shadowId:
                    raise InvalidRequest(
                        'Task Runner "%s" is running shadow task %s '
                        'but wants to set report for %s'
                        % (taskRunner.getId(), runningShadowId, shadowId)
                        )
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

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'tr/*', 'set tasks reports')

    def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.ok)

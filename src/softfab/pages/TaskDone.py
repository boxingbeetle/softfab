# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, cast
import logging

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.authentication import TokenAuthPage
from softfab.joblib import jobDB
from softfab.pageargs import (
    DictArg, DictArgInstance, EnumArg, ListArg, PageArgs, StrArg
)
from softfab.request import Request
from softfab.resourcelib import runnerFromToken
from softfab.response import Response
from softfab.resultcode import ResultCode
from softfab.resultlib import putData
from softfab.shadowlib import ExtractionRun, shadowDB
from softfab.taskrunlib import defaultSummaries
from softfab.tokens import TokenRole, TokenUser
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml


class TaskDone_POST(ControlPage['TaskDone_POST.Arguments',
                                'TaskDone_POST.Processor']):
    authenticator = TokenAuthPage(TokenRole.RESOURCE)

    class Arguments(PageArgs):
        result = EnumArg(ResultCode, None)
        summary = StrArg(None)
        report = ListArg()
        id = StrArg(None)
        name = StrArg(None)
        output = DictArg(StrArg())
        data = DictArg(StrArg())
        shadowId = StrArg(None)
        extraction = DictArg(StrArg())

    class Processor(PageProcessor['TaskDone_POST.Arguments']):

        def process(self,
                    req: Request['TaskDone_POST.Arguments'],
                    user: User
                    ) -> None:
            # Verify arguments.
            try:
                result = req.args.result
                if result is not None and result not in defaultSummaries:
                    raise InvalidRequest(
                        'Result code "%s" is for internal use only' % result
                        )
                summary = req.args.summary
                reports = req.args.report
                outputs = cast(Mapping[str, str], req.args.output)

                # Find Task Runner.
                assert isinstance(user, TokenUser), user
                try:
                    taskRunner = runnerFromToken(user)
                except KeyError as ex:
                    raise InvalidRequest(*ex.args) from ex

                shadowId = req.args.shadowId
                if shadowId is None:
                    # Execution run.
                    jobId = req.args.id
                    if jobId is None:
                        raise InvalidRequest(
                            'Either "id" or "shadowId" must be provided'
                            )
                    runningTask = taskRunner.getRun()
                    if runningTask is None:
                        raise InvalidRequest(
                            'Task Runner "%s" is not running a task'
                            % taskRunner.getId()
                            )
                    try:
                        job = jobDB[jobId]
                    except KeyError:
                        raise InvalidRequest(
                            'No job exists with ID "%s"' % jobId
                            )
                    taskName = req.args.name
                    if taskName is None:
                        raise InvalidRequest(
                            '"name" is required with "id"'
                            )
                    task = job.getTask(taskName)
                    if task is None:
                        raise InvalidRequest(
                            'No task "%s" in job "%s"' % (taskName, jobId)
                            )
                    runId = cast(str, task['run'])
                    if runningTask.getId() != runId:
                        raise InvalidRequest(
                            'Task Runner "%s" is running task %s '
                            'but wants to set %s as done'
                            % (taskRunner.getId(), runningTask.getId(), runId)
                            )

                    for report in reports:
                        # Reject anything that looks like a path separator.
                        for tabooChar in ('/', '\\', ':'):
                            if tabooChar in report:
                                raise InvalidRequest(
                                    f'Invalid character "{tabooChar}" in '
                                    f'report name "{report}"'
                                    )
                else:
                    # Shadow run.
                    if reports:
                        raise InvalidRequest(
                            'Defining reports in extraction is not supported'
                            )
                    if outputs:
                        raise InvalidRequest(
                            'Defining outputs in extraction is not supported'
                            )

                    try:
                        extResultStr = cast(str, cast(
                            DictArgInstance[str], req.args.extraction
                            )['result'])
                    except KeyError:
                        raise InvalidRequest(
                            'Missing extraction result code'
                            )
                    try:
                        extResult = ResultCode[extResultStr.upper()]
                        if extResult not in defaultSummaries:
                            raise ValueError('Internal-only result code')
                    except ValueError as ex:
                        raise InvalidRequest(
                            'Invalid result code "%s": %s' % (extResult, ex)
                            )

                    runningShadowId = taskRunner.getShadowRunId()
                    if runningShadowId is None:
                        raise InvalidRequest(
                            'Task Runner "%s" is not running a shadow task'
                            % taskRunner.getId()
                            )
                    elif runningShadowId != shadowId:
                        raise InvalidRequest(
                            'Task Runner "%s" is running shadow task %s '
                            'but wants to set %s as done'
                            % (taskRunner.getId(), runningShadowId, shadowId)
                            )

                    try:
                        shadowRun = shadowDB[shadowId]
                    except KeyError:
                        raise InvalidRequest(
                            'Shadow run "%s" does not exist' % shadowId
                            )
                    assert isinstance(shadowRun, ExtractionRun), shadowRun
                    taskRun = shadowRun.taskRun
                    taskName = taskRun.getName()
                    runId = taskRun.getId()

                extracted = cast(Mapping[str, str], req.args.data)

            except InvalidRequest as ex:
                logging.warning('Invalid TaskDone request: %s', ex)
                raise

            # Start making changes.
            if extracted:
                putData(taskName, runId, extracted)
            if shadowId is None:
                job.taskDone(taskName, result, summary, reports, outputs)
            else:
                if extResult is not ResultCode.ERROR:
                    taskRun.setResult(result, summary)
                # This must be done last, because TaskRun listens
                # to ExtractionRun and if ExtractionRun is finished without
                # setting a result, TaskRun will assume that result will
                # not come.
                shadowRun.done(extResult)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'tr/*', 'set tasks results')

    def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.ok)

# SPDX-License-Identifier: BSD-3-Clause

import logging

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.authentication import NoAuthPage
from softfab.joblib import jobDB
from softfab.pageargs import DictArg, EnumArg, PageArgs, StrArg
from softfab.resultcode import ResultCode
from softfab.resultlib import putData
from softfab.shadowlib import shadowDB
from softfab.taskrunlib import defaultSummaries
from softfab.xmlgen import xml


class TaskDone_POST(ControlPage['TaskDone_POST.Arguments', 'TaskDone_POST.Processor']):
    authenticator = NoAuthPage

    class Arguments(PageArgs):
        result = EnumArg(ResultCode, None)
        summary = StrArg(None)
        id = StrArg(None)
        name = StrArg(None)
        output = DictArg(StrArg())
        data = DictArg(StrArg())
        shadowId = StrArg(None)
        extraction = DictArg(StrArg())

    class Processor(PageProcessor):

        def process(self, req):
            # Verify arguments.
            try:
                result = req.args.result
                if result is not None and result not in defaultSummaries:
                    raise InvalidRequest(
                        'Result code "%s" is for internal use only' % result
                        )
                summary = req.args.summary
                outputs = req.args.output

                shadowId = req.args.shadowId
                if shadowId is None:
                    # Execution run.
                    jobId = req.args.id
                    if jobId is None:
                        raise InvalidRequest(
                            'Either "id" or "shadowId" must be provided'
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
                    runId = task['run']
                else:
                    # Shadow run.
                    shadowRun = shadowDB[shadowId]
                    taskRun = shadowRun.taskRun
                    taskName = taskRun.getName()
                    runId = taskRun.getId()

                    if outputs:
                        raise InvalidRequest(
                            'Defining outputs in extraction is not supported'
                            )

                    try:
                        extResult = req.args.extraction['result']
                    except KeyError:
                        raise InvalidRequest(
                            'Missing extraction result code'
                            )
                    try:
                        extResult = ResultCode.__members__[extResult.upper()]
                        if extResult not in defaultSummaries:
                            raise ValueError('Internal-only result code')
                    except ValueError as ex:
                        raise InvalidRequest(
                            'Invalid result code "%s": %s' % (extResult, ex)
                            )

                extracted = req.args.data

            except InvalidRequest as ex:
                logging.warning('Invalid TaskDone request: %s', ex)
                raise

            # Start making changes.
            if extracted:
                putData(taskName, runId, extracted)
            if shadowId is None:
                job.taskDone(taskName, result, summary, outputs)
            else:
                if extResult is not ResultCode.ERROR:
                    taskRun.setResult(result, summary)
                # This must be done last, because TaskRun listens
                # to ExtractionRun and if ExtractionRun is finished without
                # setting a result, TaskRun will assume that result will
                # not come.
                shadowRun.done(extResult)

    def checkAccess(self, user):
        pass

    def writeReply(self, response, proc):
        response.write(xml.ok)

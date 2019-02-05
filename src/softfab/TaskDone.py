# SPDX-License-Identifier: BSD-3-Clause

from ControlPage import ControlPage
from Page import InvalidRequest, PageProcessor
from authentication import NoAuthPage
from joblib import jobDB
from pageargs import DictArg, EnumArg, PageArgs, StrArg
from resultcode import ResultCode
from resultlib import putData
from shadowlib import shadowDB
from taskrunlib import defaultSummaries
from xmlgen import xml

import logging

class TaskDone_POST(ControlPage):
    authenticationWrapper = NoAuthPage

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

    def checkAccess(self, req):
        pass

    def writeReply(self, response, proc):
        response.write(xml.ok)

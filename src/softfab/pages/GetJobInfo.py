# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.joblib import jobDB
from softfab.pagelinks import JobIdArgs
from softfab.productdeflib import ProductType
from softfab.projectlib import project
from softfab.response import Response
from softfab.taskrunnerlib import taskRunnerDB
from softfab.timeview import formatTimeAttr
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml


class GetJobInfo_GET(ControlPage['GetJobInfo_GET.Arguments',
                                 'GetJobInfo_GET.Processor']):

    class Arguments(JobIdArgs):
        pass

    class Processor(PageProcessor[JobIdArgs]):

        def process(self, req, user):
            jobId = req.args.jobId
            try:
                # pylint: disable=attribute-defined-outside-init
                self.job = jobDB[jobId]
            except KeyError:
                raise InvalidRequest('Job "%s" does not exist' % jobId)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/a')

    def writeReply(self, response: Response, proc: Processor) -> None:
        taskprio = project['taskprio']

        def taskToXML(task):
            # TODO: Include info about extraction run?
            return xml.task(
                name = task['name'],
                priority = task['priority'] if taskprio else None,
                execstate = task['state'],
                result = task.getResult(),
                alert = task.getAlert(),
                summary = task['summary'],
                report = task.getURL(),
                starttime = formatTimeAttr(task['starttime']),
                duration = task['duration'],
                runner = task['runner'],
                )[
                ( xml.param(name = name, value = value)
                  for name, value in task.getVisibleParameters().items() )
                ]

        def productToXML(product, listProducers):
            prodType = product.getType()
            return xml.product(
                name = product['name'],
                type = prodType,
                state = product['state'],
                local = str(product.isLocal()).lower(),
                combined = str(product.isCombined()).lower(),
                localat = product.get('localAt'),
                locator = None if prodType is ProductType.TOKEN
                    else product.get('locator'),
                )[
                ( xml.producer(
                    name = name,
                    locator = None if prodType is ProductType.TOKEN else locator
                    )
                    for name, locator in product.getProducers()
                    ) if listProducers else None
                ]

        job = proc.job
        job.updateSummaries(taskRunnerDB)
        comment = job.comment
        tasks = job.getTaskSequence()
        response.writeXML(
            xml.job(
                jobid = job.getId(),
                target = job['target'],
                createtime = formatTimeAttr(job['timestamp']),
                configid = job['configId'],
                owner = job['owner'],
                scheduledby = job['scheduledby'],
                )
            [
            xml.comment[ comment ] if comment else None,
            ( taskToXML(task) for task in tasks ),
            xml.inputs[
                ( productToXML(prod, False) for prod in job.getInputs() )
                ],
            xml.outputs[
                ( productToXML(prod, True) for prod in job.getProduced() )
                ],
            ])

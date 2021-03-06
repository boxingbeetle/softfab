# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.joblib import JobDB, Task
from softfab.pagelinks import JobIdArgs
from softfab.productdeflib import ProductType
from softfab.productlib import Product
from softfab.request import Request
from softfab.resourcelib import ResourceDB
from softfab.response import Response
from softfab.timeview import formatTimeAttr
from softfab.users import User, checkPrivilege
from softfab.xmlgen import XML, xml


class GetJobInfo_GET(ControlPage['GetJobInfo_GET.Arguments',
                                 'GetJobInfo_GET.Processor']):

    class Arguments(JobIdArgs):
        pass

    class Processor(PageProcessor[JobIdArgs]):

        jobDB: ClassVar[JobDB]
        resourceDB: ClassVar[ResourceDB]

        async def process(self, req: Request[JobIdArgs], user: User) -> None:
            jobId = req.args.jobId
            try:
                # pylint: disable=attribute-defined-outside-init
                self.job = self.jobDB[jobId]
            except KeyError:
                raise InvalidRequest(f'Job "{jobId}" does not exist')

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/a')

    async def writeReply(self, response: Response, proc: Processor) -> None:
        taskprio = proc.project['taskprio']

        def taskToXML(task: Task) -> XML:
            run = task.getLatestRun()
            return xml.task(
                name = task.getName(),
                priority = task.getPriority() if taskprio else None,
                waiting = run.isWaiting(),
                running = run.isRunning(),
                done = run.isDone(),
                cancelled = run.isCancelled(),
                result = task.result,
                alert = task.getAlert(),
                summary = run.getSummary(),
                report = task.getURL(),
                starttime = formatTimeAttr(task.startTime),
                duration = task.getDuration(),
                runner = run.getTaskRunnerId(),
                )[
                ( xml.param(name = name, value = value)
                  for name, value in task.getVisibleParameters().items() )
                ]

        def productToXML(product: Product, listProducers: bool) -> XML:
            prodType = product.getType()
            return xml.product(
                name = product.getName(),
                type = prodType,
                available = product.isAvailable(),
                blocked = product.isBlocked(),
                local = product.isLocal(),
                combined = product.isCombined(),
                localat = product.getLocalAt(),
                locator = None if prodType is ProductType.TOKEN
                    else product.getLocator(),
                )[
                ( xml.producer(
                    name = name,
                    locator = None if prodType is ProductType.TOKEN else locator
                    )
                    for name, locator in product.getProducers()
                    ) if listProducers else None
                ]

        job = proc.job
        job.updateSummaries(list(proc.resourceDB.iterTaskRunners()))
        comment = job.comment
        tasks = job.getTaskSequence()
        response.writeXML(
            xml.job(
                jobid = job.getId(),
                target = job.getTarget(),
                createtime = formatTimeAttr(job.getCreateTime()),
                configid = job.configId,
                owner = job.owner,
                scheduledby = job.getScheduledBy(),
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

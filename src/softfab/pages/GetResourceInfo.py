# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, List, Optional, cast

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.pageargs import PageArgs, SetArg
from softfab.querylib import RecordProcessor, SetFilter, runQuery
from softfab.request import Request
from softfab.resourcelib import ResourceBase, TaskRunner, resourceDB
from softfab.response import Response
from softfab.restypelib import resTypeDB
from softfab.timeview import formatTimeAttr
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import XML, xml


class GetResourceInfo_GET(ControlPage['GetResourceInfo_GET.Arguments',
                                      'GetResourceInfo_GET.Processor']):

    class Arguments(PageArgs):
        type = SetArg()
        name = SetArg()

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'r/l')

    class Processor(PageProcessor['GetResourceInfo_GET.Arguments']):

        async def process(self,
                          req: Request['GetResourceInfo_GET.Arguments'],
                          user: User
                          ) -> None:
            resTypeNames = req.args.type
            resNames = req.args.name

            # Check validity of optional typenames
            invalidTypeNames = sorted(
                name for name in resTypeNames if name not in resTypeDB
                )
            if invalidTypeNames:
                raise InvalidRequest(
                    'Non-existing resource types: ' +
                    ', '.join(invalidTypeNames)
                    )

            # Check validity of optional names
            invalidNames = [
                name
                for name in resNames
                if name not in resourceDB
                ]
            if invalidNames:
                raise InvalidRequest(
                    'Non-existing resource names: ' +
                    ', '.join(sorted(invalidNames))
                    )

            # Determine set of resource types
            query: List[RecordProcessor] = []
            if resTypeNames:
                # TODO: Use SetFilter.create().
                query.append(SetFilter('type', resTypeNames, resourceDB))
            resources = runQuery(query, resourceDB)

            # Filter out resources with id's other than in 'resNames' if
            # filter is present
            # TODO: This could also be done using querylib.
            if resNames:
                resources = [
                    res
                    for res in resources
                    if res.getId() in resNames
                    ]

            # pylint: disable=attribute-defined-outside-init
            self.resources = resources

    async def writeReply(self, response: Response, proc: Processor) -> None:

        def iterChangedBy(resource: ResourceBase) -> Iterator[XML]:
            user = resource.getChangedUser()
            if user:
                # Currently 'user' is always 'None' for custom resources
                yield xml.changedby(
                    name = user,
                    time = formatTimeAttr(resource.getChangedTime()),
                    )

        def iterReservedBy(resource: ResourceBase) -> Iterator[XML]:
            if isinstance(resource, TaskRunner):
                # Resource is a Task Runner.
                runner = resource
                run = runner.getRun()
                if run:
                    yield xml.reservedby[
                        xml.taskref(
                            taskname = run.getName(),
                            jobid = run.getJob().getId(),
                            )
                        ]
            else:
                # Resource is of a custom type.
                if resource.isReserved():
                    yield xml.reservedby[
                        xml.userref(
                            userid = cast(str, resource['reserved'])
                            )
                        ]

        def iterResourceContent(resource: ResourceBase) -> Iterator[XML]:
            # Resource type independent information
            for cap in resource.capabilities:
                yield xml.capability(name = cap)
            yield from iterChangedBy(resource)
            yield from iterReservedBy(resource)
            if isinstance(resource, TaskRunner):
                # Include Task Runner specific infomation.
                yield xml.taskrunner(
                    connectionstatus = resource.getConnectionStatus(),
                    version = cast(str, resource['runnerVersion']),
                    exitonidle = resource.shouldExit(),
                    lastsync = cast(Optional[int], resource['lastSync']),
                    )
            else:
                # Include information on custom resource type.
                yield xml.custom(
                    description = resource.description
                    )

        response.writeXML(xml.resources[(
            xml.resource(
                # Resource type independent information
                type = resource.typeName,
                name = resource.getId(),
                suspended = resource.isSuspended(),
                locator = resource.getParameter('locator')
                )[iterResourceContent(resource)]
            for resource in proc.resources
            )])

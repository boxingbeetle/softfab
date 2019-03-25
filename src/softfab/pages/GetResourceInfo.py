# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.pageargs import PageArgs, SetArg
from softfab.querylib import SetFilter, runQuery
from softfab.resourcelib import resourceDB
from softfab.response import Response
from softfab.restypelib import resTypeDB, taskRunnerResourceTypeName
from softfab.taskrunnerlib import taskRunnerDB
from softfab.timeview import formatTimeAttr
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml


class GetResourceInfo_GET(ControlPage['GetResourceInfo_GET.Arguments',
                                      'GetResourceInfo_GET.Processor']):

    class Arguments(PageArgs):
        type = SetArg()
        name = SetArg()

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'tr/a')
        checkPrivilege(user, 'tr/l')

    class Processor(PageProcessor['GetResourceInfo_GET.Arguments']):

        def process(self, req, user):
            resTypeNames = req.args.type
            resNames = req.args.name

            # Check validity of optional typenames
            invalidTypeNames = sorted(
                name for name in resTypeNames if name not in resTypeDB
                )
            if invalidTypeNames:
                raise InvalidRequest(
                    'Non-existing resource types: %s'
                    % ', '.join(invalidTypeNames)
                    )

            # Check validity of optional names
            invalidNames = [
                name
                for name in resNames
                if name not in resourceDB and name not in taskRunnerDB
                ]
            if invalidNames:
                raise InvalidRequest(
                    'Non-existing resource names: %s'
                    % ', '.join(sorted(invalidNames))
                    )

            # Determine set of resource types
            if resTypeNames:
                query = [ SetFilter('type', resTypeNames, resourceDB) ]
                resources = runQuery(query, resourceDB)
                if taskRunnerResourceTypeName in resTypeNames:
                    resources.extend(taskRunnerDB)
            else:
                resources = list(resourceDB) + list(taskRunnerDB)

            # Filter out resources with id's other than in 'resNames' if
            # filter is present
            if resNames:
                resources = [
                    res
                    for res in resources
                    if res.getId() in resNames
                    ]

            # pylint: disable=attribute-defined-outside-init
            self.resources = resources

    def writeReply(self, response: Response, proc: Processor) -> None:

        def iterChangedBy(resource):
            user = resource['changeduser']
            if user:
                # Currently 'user' is always 'None' for custom resources
                yield xml.changedby(
                    name = user,
                    time = formatTimeAttr(resource['changedtime']),
                    )

        def iterReservedBy(resource):
            if resource['type'] == taskRunnerResourceTypeName:
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
                    shadowRunId = runner.getShadowRunId()
                    if shadowRunId:
                        yield xml.reservedby[
                            xml.shadowref(
                                shadowid = shadowRunId,
                            )
                        ]
            else:
                # Resource is of a custom type.
                if not resource.isFree():
                    yield xml.reservedby[
                        xml.userref(
                            userid = resource['reserved']
                            )
                        ]

        def iterResourceContent(resource):
            # Resource type independent information
            for cap in resource['capabilities']:
                yield xml.capability(name = cap)
            yield iterChangedBy(resource)
            yield iterReservedBy(resource)
            if resource['type'] == taskRunnerResourceTypeName:
                # Include Task Runner specific infomation.
                runner = resource
                yield xml.taskrunner(
                    connectionstatus = runner.getConnectionStatus(),
                    version = runner['runnerVersion'],
                    target = runner['target'],
                    exitonidle = str(runner.shouldExit()).lower(),
                    lastsync = runner['lastSync'],
                    )
            else:
                # Include information on custom resource type.
                yield xml.custom(
                    description = resource['description']
                    )

        response.write(xml.resources[(
            xml.resource(
                # Resource type independent information
                type = resource['type'],
                name = resource.getId(),
                suspended = str(resource.isSuspended()).lower(),
                locator = resource['locator']
                )[iterResourceContent(resource)]
            for resource in proc.resources
            )])

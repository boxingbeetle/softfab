# SPDX-License-Identifier: BSD-3-Clause

from ControlPage import ControlPage
from Page import InvalidRequest, PageProcessor
from pageargs import EnumArg, PageArgs, SetArg
from taskrunnerlib import taskRunnerDB
from xmlgen import xml

from enum import Enum

Actions = Enum('Actions', 'SUSPEND RESUME')

class ResourceControl_POST(ControlPage):

    class Arguments(PageArgs):
        name = SetArg()
        action = EnumArg(Actions)

    def checkAccess(self, req):
        req.checkPrivilege('tr/m')

    class Processor(PageProcessor):

        def process(self, req):
            resNames = req.args.name
            suspend = req.args.action is Actions.SUSPEND

            if not resNames:
                raise InvalidRequest('No resources given')

            invalidNames = []
            resources = []
            for name in resNames:
                try:
                    resources.append(taskRunnerDB[name])
                except KeyError:
                    invalidNames.append(name)
            if invalidNames:
                raise InvalidRequest(
                    'Non-existing resource names: %s'
                    % ', '.join(sorted(invalidNames))
                    )

            userName = req.getUserName()
            for res in resources:
                res.setSuspend(suspend, userName)

    def writeReply(self, response, proc):
        response.write(xml.ok)

# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.pageargs import EnumArg, PageArgs, SetArg
from softfab.taskrunnerlib import taskRunnerDB
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml

Actions = Enum('Actions', 'SUSPEND RESUME')

class ResourceControl_POST(ControlPage['ResourceControl_POST.Arguments', 'ResourceControl_POST.Processor']):

    class Arguments(PageArgs):
        name = SetArg()
        action = EnumArg(Actions)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'tr/m')

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

            userName = req.userName
            for res in resources:
                res.setSuspend(suspend, userName)

    def writeReply(self, response, proc):
        response.write(xml.ok)

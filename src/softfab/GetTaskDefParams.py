# SPDX-License-Identifier: BSD-3-Clause

from ControlPage import ControlPage
from pageargs import PageArgs, SetArg
from taskdeflib import taskDefDB
from xmlgen import xml

class GetTaskDefParams(ControlPage):

    class Arguments(PageArgs):
        param = SetArg()

    def checkAccess(self, req):
        req.checkPrivilege('td/l', 'list task definitions')
        req.checkPrivilege('td/a', 'access task definitions')

    def writeReply(self, response, proc):
        requestedParams = proc.args.param

        def externalizeParams(taskParams):
            for param in requestedParams or taskParams:
                value = taskParams.get(param)
                if value is not None:
                    yield xml.param(name = param, value = value)

        response.write(
            xml.taskdefs[(
                xml.taskdef(name = taskId)[
                    externalizeParams(taskDef.getParameters())
                    ]
                for taskId, taskDef in taskDefDB.items()
                )]
            )

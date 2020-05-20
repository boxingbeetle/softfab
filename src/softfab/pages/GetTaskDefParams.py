# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Mapping

from softfab.ControlPage import ControlPage
from softfab.pageargs import PageArgs, SetArg
from softfab.response import Response
from softfab.taskdeflib import TaskDefDB
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import XMLContent, xml


class GetTaskDefParams_GET(ControlPage['GetTaskDefParams_GET.Arguments',
                                       'GetTaskDefParams_GET.Processor']):

    class Arguments(PageArgs):
        param = SetArg()

    class Processor(ControlPage.Processor):
        taskDefDB: ClassVar[TaskDefDB]

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'td/l', 'list task definitions')
        checkPrivilege(user, 'td/a', 'access task definitions')

    async def writeReply(self, response: Response, proc: Processor) -> None:
        args: GetTaskDefParams_GET.Arguments = proc.args
        requestedParams = args.param

        def externalizeParams(taskParams: Mapping[str, str]) -> XMLContent:
            for param in requestedParams or taskParams:
                value = taskParams.get(param)
                if value is not None:
                    yield xml.param(name = param, value = value)

        response.writeXML(
            xml.taskdefs[(
                xml.taskdef(name = taskId)[
                    externalizeParams(taskDef.getParameters())
                    ]
                for taskId, taskDef in proc.taskDefDB.items()
                )]
            )

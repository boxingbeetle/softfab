# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, cast

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.configlib import configDB
from softfab.joblib import jobDB
from softfab.pageargs import DictArg, PageArgs, StrArg
from softfab.request import Request
from softfab.response import Response
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml


class LoadExecuteDefault_POST(ControlPage['LoadExecuteDefault_POST.Arguments',
                                          'LoadExecuteDefault_POST.Processor']):

    class Arguments(PageArgs):
        config = StrArg()
        prod = DictArg(StrArg())
        local = DictArg(StrArg())
        param = DictArg(StrArg())
        comment = StrArg('')

    class Processor(PageProcessor['LoadExecuteDefault_POST.Arguments']):

        async def process(self,
                          req: Request['LoadExecuteDefault_POST.Arguments'],
                          user: User
                          ) -> None:
            args = req.args
            products = cast(Mapping[str, str], args.prod)
            localAt = cast(Mapping[str, str], args.local)
            params = cast(Mapping[str, str], args.param)
            if 'notify' in params and ':' not in params['notify']:
                raise InvalidRequest('Invalid value of \'notify\' parameter')
            try:
                jobConfig = configDB[args.config]
            except KeyError:
                raise InvalidRequest(
                    f'Configuration "{args.config}" does not exist'
                    )
            else:
                for job in jobConfig.createJobs(
                        user.name, None, products, params, localAt
                        ):
                    job.comment += '\n' + args.comment
                    jobDB.add(job)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/c', 'start jobs')

    async def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(xml.ok)

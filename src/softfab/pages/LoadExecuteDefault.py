# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.configlib import configDB
from softfab.joblib import jobDB
from softfab.pageargs import DictArg, PageArgs, StrArg
from softfab.userlib import checkPrivilege
from softfab.xmlgen import xml


class LoadExecuteDefault_POST(ControlPage['LoadExecuteDefault_POST.Arguments', 'LoadExecuteDefault_POST.Processor']):

    class Arguments(PageArgs):
        config = StrArg()
        prod = DictArg(StrArg())
        local = DictArg(StrArg())
        param = DictArg(StrArg())
        comment = StrArg('')

    class Processor(PageProcessor):

        def process(self, req):
            args = req.args
            if 'notify' in args.param and ':' not in args.param['notify']:
                raise InvalidRequest('Invalid value of \'notify\' parameter')
            try:
                jobConfig = configDB[args.config]
            except KeyError:
                raise InvalidRequest(
                    'Configuration "%s" does not exist' % args.config
                    )
            else:
                job = jobConfig.createJob(
                    req.userName, None, args.prod, args.param, args.local
                    )
                job.comment += '\n' + args.comment
                jobDB.add(job)

    def checkAccess(self, req):
        checkPrivilege(req.user, 'j/c', 'start jobs')

    def writeReply(self, response, proc):
        response.write(xml.ok)

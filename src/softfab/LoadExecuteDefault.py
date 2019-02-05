# SPDX-License-Identifier: BSD-3-Clause

from ControlPage import ControlPage
from Page import InvalidRequest, PageProcessor
from configlib import configDB
from joblib import jobDB
from pageargs import DictArg, PageArgs, StrArg
from xmlgen import xml

class LoadExecuteDefault_POST(ControlPage):

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
                    req.getUserName(), None, args.prod, args.param, args.local
                    )
                job.comment += '\n' + args.comment
                jobDB.add(job)

    def checkAccess(self, req):
        req.checkPrivilege('j/c', 'start jobs')

    def writeReply(self, response, proc):
        response.write(xml.ok)

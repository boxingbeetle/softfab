# SPDX-License-Identifier: BSD-3-Clause

from ControlPage import ControlPage
from Page import InvalidRequest, PageProcessor
from pagelinks import TaskRunnerIdArgs
from taskrunnerlib import taskRunnerDB
from xmlgen import xml

class TaskRunnerExit_POST(ControlPage):

    class Arguments(TaskRunnerIdArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            runnerId = req.args.runnerId
            runner = taskRunnerDB.get(runnerId)
            if runner is None:
                raise InvalidRequest(
                    'Task Runner "%s" does not exist' % runnerId
                    )
            runner.setExitFlag(True)

    def checkAccess(self, req):
        req.checkPrivilege('tr/m', 'control Task Runners')

    def writeReply(self, response, proc):
        response.write(xml.ok)
        # TODO: Write error body in addition to result code.
        #response.write(xml.error(message = error))

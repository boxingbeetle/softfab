# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.pagelinks import TaskRunnerIdArgs
from softfab.taskrunnerlib import taskRunnerDB
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml


class TaskRunnerExit_POST(ControlPage['TaskRunnerExit_POST.Arguments', 'TaskRunnerExit_POST.Processor']):

    class Arguments(TaskRunnerIdArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req, user):
            runnerId = req.args.runnerId
            runner = taskRunnerDB.get(runnerId)
            if runner is None:
                raise InvalidRequest(
                    'Task Runner "%s" does not exist' % runnerId
                    )
            runner.setExitFlag(True)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'tr/m', 'control Task Runners')

    def writeReply(self, response, proc):
        response.write(xml.ok)
        # TODO: Write error body in addition to result code.
        #response.write(xml.error(message = error))

# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, Optional, cast

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor, SavePhase
)
from softfab.Page import InvalidRequest
from softfab.databaselib import Database
from softfab.formlib import SingleCheckBoxTable
from softfab.pageargs import BoolArg, StrArg
from softfab.resourcelib import TaskRunner, resourceDB
from softfab.resourceview import CapabilitiesPanel, CommentPanel
from softfab.webgui import Table, vgroup
from softfab.xmlgen import XMLContent, xhtml


class TaskRunnerEditArgs(EditArgs):
    capabilities = StrArg('')
    description = StrArg('')
    resetpass = BoolArg()

class TaskRunnerSavePhase(SavePhase[TaskRunnerEditArgs, TaskRunner]):

    def addRecord(self,
            proc: EditProcessor[TaskRunnerEditArgs, TaskRunner],
            element: TaskRunner
            ) -> None:
        super().addRecord(proc, element)
        self.resetTokenPassword(proc, element)

    def updateRecord(self,
            proc: EditProcessor[TaskRunnerEditArgs, TaskRunner],
            element: TaskRunner
            ) -> None:
        super().updateRecord(proc, element)
        self.resetTokenPassword(proc, element)

    def resetTokenPassword(self,
            proc: EditProcessor[TaskRunnerEditArgs, TaskRunner],
            element: TaskRunner
            ) -> None:
        token = element.token
        proc.tokenId = token.getId() # type: ignore
        if proc.args.resetpass:
            proc.password = token.resetPassword() # type: ignore
        else:
            proc.password = None # type: ignore

    def presentContent(self,
            proc: EditProcessor[TaskRunnerEditArgs, TaskRunner]
            ) -> XMLContent:
        yield TokenTable.instance.present(proc=proc)
        yield super().presentContent(proc)

class TaskRunnerEditBase(EditPage[TaskRunnerEditArgs, TaskRunner]):
    # FabPage constants:
    icon = 'IconResources'
    description = 'Edit Task Runner'
    linkDescription = False

    # EditPage constants:
    elemTitle = 'Task Runner'
    elemName = 'Task Runner'
    db = cast(Database[TaskRunner], resourceDB)
    privDenyText = 'Task Runners'
    useScript = False
    formId = 'runner'
    autoName = None

    def getFormContent(self, proc: EditProcessorBase) -> XMLContent:
        args = proc.args
        if args.id != '':
            yield xhtml.h2[ 'Task Runner: ', xhtml.b[ args.id ]]
        yield vgroup[
            CapabilitiesPanel.instance,
            CommentPanel.instance,
            ResetPassPanel.instance
            ]

class TaskRunnerEdit_GET(TaskRunnerEditBase):

    class Arguments(InitialEditArgs):
        pass

    class Processor(InitialEditProcessor[TaskRunnerEditArgs, TaskRunner]):
        argsClass = TaskRunnerEditArgs

        def _initArgs(self,
                      element: Optional[TaskRunner]
                      ) -> Mapping[str, object]:
            if element is None:
                return {'resetpass': True}
            elif isinstance(element, TaskRunner):
                return dict(
                    capabilities = ' '.join(element.capabilities),
                    description = element['description']
                    )
            else:
                raise InvalidRequest(
                    'Resource "%s" is not a Task Runner' % element.getId()
                    )

class TaskRunnerEdit_POST(TaskRunnerEditBase):

    class Arguments(TaskRunnerEditArgs):
        pass

    class Processor(EditProcessor[TaskRunnerEditArgs, TaskRunner]):

        def createElement(self,
                          recordId: str,
                          args: TaskRunnerEditArgs,
                          oldElement: Optional[TaskRunner]
                          ) -> TaskRunner:
            element = TaskRunner.create(
                recordId,
                args.description,
                args.capabilities.split()
                )
            if isinstance(oldElement, TaskRunner) \
                    and oldElement.getId() == recordId:
                # Preserve resource state.
                # Do this only when a resource is overwritten by itself, not
                # if one resource overwrites another or if a new resource is
                # created using Save As.
                element.copyState(oldElement)
            return element

    def __init__(self):
        super().__init__()
        self.savePhase = TaskRunnerSavePhase(self)

class ResetPassPanel(SingleCheckBoxTable):
    name = 'resetpass'
    label = 'Set new password for access token'

class TokenTable(Table):
    columns = None, None

    def iterRows(self, *, proc, **kwargs):
        tokenId = getattr(proc, 'tokenId') # type: str
        password = getattr(proc, 'password') # type: Optional[str]
        yield 'Access token ID: ', xhtml.code[tokenId]
        if password is not None:
            yield 'Access token password: ', xhtml.code[password]

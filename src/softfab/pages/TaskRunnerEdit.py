# SPDX-License-Identifier: BSD-3-Clause

from typing import Optional

from softfab.EditPage import EditPage, SavePhase
from softfab.Page import InvalidRequest
from softfab.formlib import SingleCheckBoxTable
from softfab.pageargs import BoolArg, StrArg
from softfab.resourcelib import TaskRunner, resourceDB
from softfab.resourceview import CapabilitiesPanel, CommentPanel
from softfab.webgui import Table, vgroup
from softfab.xmlgen import XMLContent, xhtml


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

class TaskRunnerSavePhase(SavePhase):

    def addRecord(self, proc, element):
        super().addRecord(proc, element)
        self.resetTokenPassword(proc, element)

    def updateRecord(self, proc, element):
        super().updateRecord(proc, element)
        self.resetTokenPassword(proc, element)

    def resetTokenPassword(self, proc, element):
        token = element.token
        proc.tokenId = token.getId()
        if proc.args.resetpass:
            proc.password = token.resetPassword()
        else:
            proc.password = None

    def presentContent(self, proc: 'EditPage.Processor') -> XMLContent:
        yield TokenTable.instance.present(proc=proc)
        yield super().presentContent(proc)

class TaskRunnerEdit(EditPage):
    # FabPage constants:
    icon = 'IconResources'
    description = 'Edit Task Runner'
    linkDescription = False

    # EditPage constants:
    elemTitle = 'Task Runner'
    elemName = 'Task Runner'
    db = resourceDB
    privDenyText = 'Task Runners'
    useScript = False
    formId = 'runner'
    autoName = None

    class Arguments(EditPage.Arguments):
        capabilities = StrArg('')
        description = StrArg('')
        resetpass = BoolArg()

    class Processor(EditPage.Processor):

        def createElement(self, req, recordId, args, oldElement):
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

        def _initArgs(self, element):
            if element is None:
                return {}
            elif isinstance(element, TaskRunner):
                return dict(
                    capabilities = ' '.join(element['capabilities']),
                    description = element['description']
                    )
            else:
                raise InvalidRequest(
                    'Resource "%s" is not a Task Runner' % element.getId()
                    )

    def __init__(self):
        super().__init__()
        self.savePhase = TaskRunnerSavePhase(self)

    def getFormContent(self, proc: Processor) -> XMLContent:
        args = proc.args
        if args.id != '':
            yield xhtml.h2[ 'Task Runner: ', xhtml.b[ args.id ]]
        yield vgroup[
            CapabilitiesPanel.instance,
            CommentPanel.instance,
            ResetPassPanel.instance
            ]

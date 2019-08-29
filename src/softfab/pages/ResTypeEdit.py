# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, Optional

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.formlib import CheckBoxesTable, textInput
from softfab.pageargs import SetArg, StrArg
from softfab.restypelib import ResType, resTypeDB
from softfab.userlib import AccessDenied
from softfab.webgui import Column, PropertiesTable, cell
from softfab.xmlgen import XMLContent


class ResTypeEditArgs(EditArgs):
    type = SetArg()
    description = StrArg('')

class ResTypeEditBase(EditPage[ResTypeEditArgs, ResType]):
    # FabPage constants:
    icon = 'IconResources'
    description = 'Edit Resource Type'
    linkDescription = 'New Resource Type'

    # EditPage constants:
    elemTitle = 'Resource Type'
    elemName = 'resource type'
    db = resTypeDB
    privDenyText = 'resource types'
    useScript = False
    formId = 'restype'
    autoName = None

    def getFormContent(self,
                       proc: EditProcessorBase[ResTypeEditArgs, ResType]
                       ) -> XMLContent:
        return ResTypeTable.instance

class ResTypeEdit_GET(ResTypeEditBase):

    class Arguments(InitialEditArgs):
        pass

    class Processor(InitialEditProcessor[ResTypeEditArgs, ResType]):
        argsClass = ResTypeEditArgs

        def _initArgs(self, element: Optional[ResType]) -> Mapping[str, object]:
            if element is None:
                return { 'type': ('pertask',) }
            else:
                return {
                    'description': element.description,
                    'type': (
                        name for name in ('pertask', 'perjob') if element[name]
                        )
                    }

class ResTypeEdit_POST(ResTypeEditBase):

    class Arguments(ResTypeEditArgs):
        pass

    class Processor(EditProcessor[ResTypeEditArgs, ResType]):

        def checkId(self, recordId: str) -> None:
            if recordId.startswith('sf.'):
                raise KeyError('names starting with "sf." are reserved')

        def createElement(self,
                          recordId: str,
                          args: ResTypeEditArgs,
                          oldElement: Optional[ResType]
                          ) -> ResType:
            if recordId.startswith('sf.'):
                raise AccessDenied(
                    'modify built-in resource types (they are immutable)'
                    )
            return ResType.create(
                name = recordId,
                pertask = 'pertask' in args.type,
                perjob = 'perjob' in args.type,
                description = args.description
                )

class ExclusiveWidget(CheckBoxesTable):
    name = 'type'
    columns = Column(cellStyle='nobreak'), None
    def iterOptions(self, **kwargs):
        yield 'pertask', (
            'per task:',
            'only one task at a time can use the resource'
            )
        yield 'perjob', (
            'per job:',
            'the resource will remain reserved between tasks in the same job'
            )
    def getActive(self, proc, **kwargs):
        return proc.args.type

class ResTypeTable(PropertiesTable):

    def iterRows(self, *, proc, **kwargs):
        yield 'Name', proc.args.id or '(unnamed)'
        yield 'Description', \
            textInput(name = 'description', size = 80).present(
                proc=proc, **kwargs
                )
        yield 'Exclusive', cell(class_ = 'checkboxes')[
            ExclusiveWidget.instance.present(proc=proc, **kwargs)
            ]

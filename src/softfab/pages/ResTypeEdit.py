# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Iterator, Mapping, Optional, Sequence, Tuple, cast

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.formlib import CheckBoxesTable, textInput
from softfab.pageargs import SetArg, StrArg
from softfab.restypelib import ResType, ResTypeDB
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
    dbName = 'resTypeDB'
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

        resTypeDB: ClassVar[ResTypeDB]

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

        resTypeDB: ClassVar[ResTypeDB]

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

    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[str, Sequence[XMLContent]]]:
        yield 'pertask', (
            'per task:',
            'only one task at a time can use the resource'
            )
        yield 'perjob', (
            'per job:',
            'the resource will remain reserved between tasks in the same job'
            )

class ResTypeTable(PropertiesTable):

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(EditProcessorBase[ResTypeEditArgs, ResType], kwargs['proc'])
        yield 'Name', proc.args.id or '(unnamed)'
        yield 'Description', textInput(name='description', size=80)
        yield 'Exclusive', cell(class_='checkboxes')[ ExclusiveWidget.instance ]

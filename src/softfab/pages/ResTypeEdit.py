# SPDX-License-Identifier: BSD-3-Clause

from softfab.EditPage import EditPage
from softfab.formlib import CheckBoxesTable, textInput
from softfab.pageargs import SetArg, StrArg
from softfab.restypelib import ResType, resTypeDB
from softfab.webgui import Column, PropertiesTable, cell

class ResTypeEdit(EditPage):
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

    class Arguments(EditPage.Arguments):
        type = SetArg()
        description = StrArg('')

    class Processor(EditPage.Processor):

        def checkId(self, recordId):
            if recordId.startswith('sf.'):
                raise KeyError('names starting with "sf." are reserved')

        def createElement(self, req, recordId, args, oldElement):
            return ResType.create(
                name = recordId,
                pertask = 'pertask' in args.type,
                perjob = 'perjob' in args.type,
                description = args.description
                )

        def _initArgs(self, element):
            if element is None:
                return { 'type': ('pertask',) }
            else:
                return {
                    'description': element.getDescription(),
                    'type': (
                        name for name in ('pertask', 'perjob') if element[name]
                        )
                    }

    def getFormContent(self, proc):
        return ResTypeTable.instance

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

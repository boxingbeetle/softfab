# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from typing import ClassVar

from softfab.EditPage import EditArgs, EditPage, EditProcessor
from softfab.Page import PresentableError
from softfab.formlib import checkBox, dropDownList, emptyOption, textInput
from softfab.frameworklib import Framework, frameworkDB
from softfab.pageargs import BoolArg, SetArg, StrArg
from softfab.paramlib import paramTop
from softfab.paramview import (
    ParamArgsMixin, ParamDefTable, addParamsToElement, checkParamState,
    initParamArgs, validateParamState
)
from softfab.productdeflib import productDefDB
from softfab.resourceview import (
    ResourceRequirementsArgsMixin, addResourceRequirementsToElement,
    checkResourceRequirementsState, initResourceRequirementsArgs,
    resourceRequirementsWidget, validateResourceRequirementsState
)
from softfab.taskdeflib import taskDefDB
from softfab.utils import abstract
from softfab.webgui import (
    PropertiesTable, Table, docLink, hgroup, rowManagerInstanceScript
)
from softfab.xmlgen import xhtml


class FrameworkEdit(EditPage):
    # FabPage constants:
    icon = 'Framework1'
    description = 'Edit Framework'
    linkDescription = 'New Framework'

    # EditPage constants:
    elemTitle = 'Framework'
    elemName = 'framework'
    db = frameworkDB
    privDenyText = 'framework definitions'
    useScript = True
    formId = 'framework'
    autoName = None

    class Arguments(
            EditArgs, ParamArgsMixin, ResourceRequirementsArgsMixin
            ):
        wrapper = StrArg('')
        extractor = BoolArg()
        input = SetArg()
        output = SetArg()

    class Processor(EditProcessor):

        def createElement(self, req, recordId, args, oldElement):
            inputs = set(args.input)
            inputs.discard('')
            outputs = set(args.output)
            outputs.discard('')
            element = Framework.create(recordId, inputs, outputs)
            addParamsToElement(element, args)
            element.addParameter('sf.wrapper', args.wrapper, True)
            element.addParameter('sf.extractor', str(args.extractor), True)
            addResourceRequirementsToElement(element, args)
            return element

        def _initArgs(self, element):
            if element is None:
                overrides = {}
            else:
                params = element.getParametersSelf()
                overrides = dict(
                    input = element.getInputs(),
                    output = element.getOutputs(),
                    wrapper = params.get('sf.wrapper', ''),
                    extractor = params.get('sf.extractor') in ('True', 'true')
                    )
                overrides.update(initParamArgs(element))
            overrides.update(initResourceRequirementsArgs(element))
            return overrides

        def _checkState(self):
            """Check against making parameters final which are overridden in
            existing task defs.
            """
            args = self.args

            # TODO: Generalize this when we support a variable number of levels.
            for index, name in args.params.items():
                if name == '':
                    continue
                final = index in args.final
                if final:
                    for task in taskDefDB:
                        if task['parent'] == args.id and \
                                name in task.getParametersSelf():
                            raise PresentableError(xhtml.p[
                                'Cannot make parameter "%s" final, '
                                'because it is overridden by task "%s".'
                                % ( name, task.getId() )
                                ])

            if args.wrapper == '':
                raise PresentableError(xhtml.p[
                    'Value of the wrapper field cannot be empty. '
                    'If you have no special wishes, '
                    'use the framework name as the wrapper name.'
                    ])

            checkParamState(args, paramTop)
            checkResourceRequirementsState(args)

        def _validateState(self):
            args = self.args
            self.args = args = args.override(
                input = args.input - { '' },
                output = args.output - { '' },
                )
            validateParamState(self, paramTop)
            validateResourceRequirementsState(self)

    def getFormContent(self, proc):
        yield FrameworkPropertiesTable.instance
        yield xhtml.ul[
            xhtml.li[
                'The wrapper field selects the directory in which to look for '
                'a wrapper script. '
                'Read ',
				docLink(
				   '/introduction/framework-and-task-definitions/#frameworkdef'
				)['the documentation'],
				' for details.'
                ],
            xhtml.li[
                'The extractor field indicates that mid-level data extraction '
                'should be performed for this framework. '
                'This requires an extractor script to be written. '
                'Read ',
				docLink(
					'/introduction/framework-and-task-definitions/#extract'
				)['the documentation'],
				' for details.'
                ]
            ]

        yield hgroup[
            InputsTable.instance,
            OutputsTable.instance
            ]

        yield ParamDefTable(paramTop)

        yield resourceRequirementsWidget()

class FrameworkPropertiesTable(PropertiesTable):

    def iterRows(self, *, proc, **kwargs):
        yield 'Name', proc.args.id or '(untitled)'
        yield 'Wrapper', textInput(name='wrapper', size=40)
        yield 'Extractor', checkBox(name='extractor')[
            'Extract mid-level data from reports using separate '
            'extraction wrapper'
            ]

class ProductSetTable(Table, ABC):
    argName = abstract # type: ClassVar[str]

    def iterRows(self, *, proc, **kwargs):
        name = self.argName
        options = [
            emptyOption[ '(none)' ]
            ] + sorted(productDefDB.uniqueValues('id'))
        for prod in sorted(getattr(proc.args, name)) + [ '' ]:
            yield dropDownList(name=name, selected=prod)[ options ],

    def present(self, **kwargs):
        yield super().present(**kwargs)
        yield rowManagerInstanceScript(bodyId=self.bodyId).present(**kwargs)

class InputsTable(ProductSetTable):
    columns = 'Inputs',
    bodyId = 'iprlist'
    argName = 'input'

class OutputsTable(ProductSetTable):
    columns = 'Outputs',
    bodyId = 'oprlist'
    argName = 'output'

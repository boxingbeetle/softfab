# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from typing import (
    ClassVar, Dict, Iterable, Iterator, List, Mapping, Optional, cast
)

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.Page import PresentableError
from softfab.formlib import checkBox, dropDownList, emptyOption, textInput
from softfab.frameworklib import Framework, frameworkDB
from softfab.pageargs import BoolArg, DictArgInstance, SetArg, StrArg
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
from softfab.xmlgen import XMLContent, xhtml


class FrameworkEditArgs(
        EditArgs, ParamArgsMixin, ResourceRequirementsArgsMixin
        ):
    wrapper = StrArg('')
    extractor = BoolArg()
    input = SetArg()
    output = SetArg()

class FrameworkEditBase(EditPage[FrameworkEditArgs, Framework]):
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

    def getFormContent(self,
                       proc: EditProcessorBase[FrameworkEditArgs, Framework]
                       ) -> XMLContent:
        yield FrameworkPropertiesTable.instance
        yield xhtml.ul[
            xhtml.li[
                'The wrapper field selects the directory in which to look for '
                'a wrapper script. '
                'Read ',
                docLink(
                   '/concepts/taskdefs/#frameworkdef'
                )['the documentation'],
                ' for details.'
                ],
            xhtml.li[
                'The extractor field indicates that mid-level data extraction '
                'should be performed for this framework. '
                'This requires an extractor script to be written. '
                'Read ',
                docLink(
                    '/concepts/taskdefs/#extract'
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

class FrameworkEdit_GET(FrameworkEditBase):

    class Arguments(InitialEditArgs):
        pass

    class Processor(InitialEditProcessor[FrameworkEditArgs, Framework]):
        argsClass = FrameworkEditArgs

        def _initArgs(self,
                      element: Optional[Framework]
                      ) -> Mapping[str, object]:
            if element is None:
                overrides = {} # type: Dict[str, object]
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

        def _validateState(self) -> None:
            # Put parameters in the right order.
            validateParamState(self, paramTop)

class FrameworkEdit_POST(FrameworkEditBase):

    class Arguments(FrameworkEditArgs):
        pass

    class Processor(EditProcessor[FrameworkEditArgs, Framework]):

        def createElement(self,
                          recordId: str,
                          args: FrameworkEditArgs,
                          oldElement: Optional[Framework]
                          ) -> Framework:
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

        def _checkState(self) -> None:
            """Check against making parameters final which are overridden in
            existing task defs.
            """
            args = self.args

            # TODO: Generalize this when we support a variable number of levels.
            for index, name in cast(DictArgInstance[str], args.params).items():
                if name == '':
                    continue
                final = index in cast(DictArgInstance[bool], args.final)
                if final:
                    for task in taskDefDB:
                        if task['parent'] == args.id and \
                                name in task.getParametersSelf():
                            raise PresentableError(xhtml.p[
                                f'Cannot make parameter "{name}" final, '
                                f'because it is overridden '
                                f'by task "{task.getId()}".'
                                ])

            if args.wrapper == '':
                raise PresentableError(xhtml.p[
                    'Value of the wrapper field cannot be empty. '
                    'If you have no special wishes, '
                    'use the framework name as the wrapper name.'
                    ])

            checkParamState(args, paramTop)
            checkResourceRequirementsState(args)

        def _validateState(self) -> None:
            self.args = self.args.override(input=self.args.input - {''},
                                           output=self.args.output - {''})
            validateParamState(self, paramTop)
            validateResourceRequirementsState(self)

class FrameworkPropertiesTable(PropertiesTable):

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        args = cast(
            EditProcessor[FrameworkEditArgs, Framework], kwargs['proc']
            ).args
        yield 'Name', args.id or '(untitled)'
        yield 'Wrapper', textInput(name='wrapper', size=40)
        yield 'Extractor', checkBox(name='extractor')[
            'Extract mid-level data from reports using separate '
            'extraction wrapper'
            ]

class ProductSetTable(Table, ABC):
    argName = abstract # type: ClassVar[str]

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        args = cast(
            EditProcessor[FrameworkEditArgs, Framework], kwargs['proc']
            ).args
        name = self.argName
        options: List[XMLContent] = [emptyOption[ '(none)' ]]
        options += sorted(cast(Iterable[str], productDefDB.uniqueValues('id')))
        products: Iterable[str] = getattr(args, name)
        for prod in sorted(products) + [ '' ]:
            yield dropDownList(name=name, selected=prod)[ options ],

    def present(self, **kwargs: object) -> XMLContent:
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

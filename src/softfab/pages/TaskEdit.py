# SPDX-License-Identifier: BSD-3-Clause

from typing import Dict, Iterator, Mapping, Optional, cast

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.Page import PresentableError
from softfab.formlib import dropDownList, emptyOption, textArea, textInput
from softfab.frameworklib import Framework, frameworkDB
from softfab.pageargs import IntArg, StrArg
from softfab.paramlib import Parameterized, paramTop
from softfab.paramview import (
    ParamArgsMixin, ParamDefTable, addParamsToElement, checkParamState,
    initParamArgs, validateParamState
)
from softfab.projectlib import project
from softfab.resourceview import (
    ResourceRequirementsArgsMixin, addResourceRequirementsToElement,
    checkResourceRequirementsState, initResourceRequirementsArgs,
    resourceRequirementsWidget, validateResourceRequirementsState
)
from softfab.selectview import textToValues, valuesToText
from softfab.taskdeflib import TaskDef, taskDefDB
from softfab.webgui import PropertiesTable
from softfab.xmlgen import XMLContent, xhtml


class TaskEditArgs(EditArgs, ParamArgsMixin, ResourceRequirementsArgsMixin):
    title = StrArg('')
    descr = StrArg('')
    framework = StrArg('')
    timeout = IntArg(0)
    requirements = StrArg('')

class TaskEditBase(EditPage[TaskEditArgs, TaskDef]):
    # FabPage constants:
    icon = 'TaskDef2'
    description = 'Edit Task Definition'
    linkDescription = 'New Task Definition'

    # EditPage constants:
    elemTitle = 'Task Definition'
    elemName = 'task definition'
    db = taskDefDB
    privDenyText = 'task definitions'
    useScript = True
    formId = 'taskdef'
    autoName = None

    def getFormContent(self,
                       proc: EditProcessorBase[TaskEditArgs, TaskDef]
                       ) -> XMLContent:
        parent = getattr(proc, 'parent')
        yield TaskPropertiesTable.instance
        yield ParamDefTable(parent)
        yield resourceRequirementsWidget(
            None
            if parent is paramTop
            else cast(Framework, parent).resourceClaim
            )

def getParent(args: TaskEditArgs) -> Parameterized:
    framework = args.framework
    if framework == '':
        return paramTop
    else:
        try:
            return frameworkDB[framework]
        except KeyError:
            # Framework no longer exists.
            return paramTop

class TaskEdit_GET(TaskEditBase):

    class Arguments(InitialEditArgs):
        pass

    class Processor(InitialEditProcessor[TaskEditArgs, TaskDef]):
        argsClass = TaskEditArgs

        def _initArgs(self, element: Optional[TaskDef]) -> Mapping[str, object]:
            if element is None:
                overrides = {} # type: Dict[str, object]
            else:
                overrides = dict(
                    title = element.getTitle(),
                    descr = element.getDescription(),
                    framework = element.getParentName() or '',
                    timeout = element.timeoutMins or 0,
                    requirements = valuesToText(element.getTagValues('sf.req')),
                    )
                overrides.update(initParamArgs(element))
            overrides.update(initResourceRequirementsArgs(element))
            return overrides

        def _validateState(self) -> None:
            parent = getParent(self.args)
            # Add parent parameters and put them all in the right order.
            validateParamState(self, parent)
            # pylint: disable=attribute-defined-outside-init
            self.parent = parent

class TaskEdit_POST(TaskEditBase):

    class Arguments(TaskEditArgs):
        pass

    class Processor(EditProcessor[TaskEditArgs, TaskDef]):

        def createElement(self,
                          recordId: str,
                          args: TaskEditArgs,
                          oldElement: Optional[TaskDef]
                          ) -> TaskDef:
            element = TaskDef.create(
                name = recordId,
                parent = args.framework or None,
                title = args.title,
                description = args.descr,
                )
            addParamsToElement(element, args)
            if args.timeout > 0:
                element.addParameter('sf.timeout', str(args.timeout), True)
            element.setTag('sf.req', textToValues(args.requirements))
            addResourceRequirementsToElement(element, args)
            return element

        def _checkState(self) -> None:
            args = self.args

            framework = args.framework
            if framework == '':
                raise PresentableError(xhtml.p[
                    'Please select a framework.'
                    ])
            else:
                try:
                    parent = frameworkDB[framework]
                except KeyError:
                    raise PresentableError(xhtml.p[
                        'Framework "%s" does not exist (anymore).'
                        % framework
                        ])

            checkParamState(args, parent)
            checkResourceRequirementsState(args)

        def _validateState(self) -> None:
            parent = getParent(self.args)

            # Filter out empty lines.
            validateParamState(self, parent)
            validateResourceRequirementsState(self)

            self.parent = parent # pylint: disable=attribute-defined-outside-init

class TaskPropertiesTable(PropertiesTable):

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        args = cast(EditProcessor[TaskEditArgs, TaskDef], kwargs['proc']).args
        yield 'Task ID', args.id or '(untitled)'
        yield 'Title', textInput(name='title', size=80)
        yield 'Description', textArea(name='descr', cols=80, rows=3)
        yield 'Framework', dropDownList(
            name='framework', required=True, onchange='form.submit()'
            )[
            emptyOption(disabled=True)[ '(select framework)' ],
            sorted(frameworkDB.keys())
            ]
        yield 'Timeout', (
            textInput(name='timeout', size=4),
            'minutes; 0 means "never".'
            )
        if project['reqtag']:
            # Note: dialog.State + formlib will take care that the requirement
            #       links are preserved when piece of UI is not shown.
            yield 'Requirements', textInput(name='requirements', size=80)

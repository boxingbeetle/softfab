# SPDX-License-Identifier: BSD-3-Clause

from typing import Dict, Mapping, Optional, cast

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.Page import PresentableError
from softfab.formlib import dropDownList, emptyOption, textArea, textInput
from softfab.frameworklib import Framework, frameworkDB
from softfab.pageargs import IntArg, StrArg
from softfab.paramlib import ParamMixin, paramTop
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
            # pylint: disable=attribute-defined-outside-init
            self.parent = paramTop # type: ParamMixin

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
            args = self.args

            # TODO: It would be better to do things like this in the
            #       constructor.
            # pylint: disable=attribute-defined-outside-init
            framework = args.framework
            if framework == '':
                self.parent = paramTop # type: ParamMixin
            else:
                try:
                    self.parent = frameworkDB[framework]
                except KeyError:
                    # Framework no longer exists.
                    self.parent = paramTop

            # Filter out empty lines.
            validateParamState(self, self.parent)
            validateResourceRequirementsState(self)

class TaskPropertiesTable(PropertiesTable):

    def iterRows(self, *, proc, **kwargs):
        yield 'Task ID', proc.args.id or '(untitled)'
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

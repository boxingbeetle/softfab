# SPDX-License-Identifier: BSD-3-Clause

from softfab.EditPage import EditPage, EditProcessor
from softfab.Page import PresentableError
from softfab.formlib import dropDownList, emptyOption, textArea, textInput
from softfab.frameworklib import frameworkDB
from softfab.pageargs import IntArg, StrArg
from softfab.paramlib import paramTop
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
from softfab.xmlgen import xhtml


class TaskEdit(EditPage):
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

    class Arguments(
            EditPage.Arguments, ParamArgsMixin, ResourceRequirementsArgsMixin
            ):
        title = StrArg('')
        descr = StrArg('')
        framework = StrArg('')
        timeout = IntArg(0)
        requirements = StrArg('')

    class Processor(EditProcessor):

        def createElement(self, req, recordId, args, oldElement):
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

        def _initArgs(self, element):
            if self.args.framework != '':
                # This is a scripted form submission from the framework
                # drop-down list; don't reload arguments.
                return {}

            if element is None:
                overrides = {}
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

        def _checkState(self):
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

        def _validateState(self):
            args = self.args

            # TODO: It would be better to do things like this in the
            #       constructor.
            # pylint: disable=attribute-defined-outside-init
            framework = args.framework
            if framework == '':
                self.parent = paramTop
            else:
                try:
                    self.parent = frameworkDB[framework]
                except KeyError:
                    # Framework no longer exists.
                    self.parent = paramTop

            # Filter out empty lines.
            validateParamState(self, self.parent)
            validateResourceRequirementsState(self)

    def getFormContent(self, proc):
        parent = proc.parent
        yield TaskPropertiesTable.instance
        yield ParamDefTable(parent)
        yield resourceRequirementsWidget(
            None if parent is paramTop else parent.resourceClaim
            )

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

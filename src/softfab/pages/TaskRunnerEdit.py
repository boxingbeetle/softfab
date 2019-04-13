# SPDX-License-Identifier: BSD-3-Clause

from softfab.EditPage import EditPage
from softfab.Page import InvalidRequest
from softfab.pageargs import StrArg
from softfab.resourcelib import TaskRunner, resourceDB
from softfab.resourceview import CapabilitiesPanel, CommentPanel
from softfab.webgui import vgroup
from softfab.xmlgen import XMLContent, xhtml

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

    def getFormContent(self, proc: Processor) -> XMLContent:
        args = proc.args
        if args.id != '':
            yield xhtml.h2[ 'Task Runner: ', xhtml.b[ args.id ]]
        yield vgroup[
            CapabilitiesPanel.instance,
            CommentPanel.instance
            ]

# SPDX-License-Identifier: BSD-3-Clause

from softfab.EditPage import EditArgs, EditPage, EditProcessor
from softfab.Page import InvalidRequest, PresentableError
from softfab.formlib import RadioTable, textInput
from softfab.pageargs import StrArg
from softfab.resourcelib import Resource, resourceDB
from softfab.resourceview import CapabilitiesPanel, CommentPanel
from softfab.restypelib import resTypeDB, taskRunnerResourceTypeName
from softfab.restypeview import ResTypeTableMixin
from softfab.webgui import Panel, pageLink, vgroup
from softfab.xmlgen import xhtml


class CustomResTypeTable(ResTypeTableMixin, RadioTable):
    reserved = False

class ResourceEdit(EditPage):
    # FabPage constants:
    icon = 'IconResources'
    description = 'Edit Resource'
    linkDescription = False

    # EditPage constants:
    elemTitle = 'Resource'
    elemName = 'resource'
    db = resourceDB
    privDenyText = 'resources'
    useScript = False
    formId = 'resource'
    autoName = None

    class Arguments(EditArgs):
        restype = StrArg('')
        capabilities = StrArg('')
        locator = StrArg('')
        description = StrArg('')

    class Processor(EditProcessor):

        def createElement(self, req, recordId, args, oldElement):
            element = Resource.create(
                recordId,
                args.restype,
                args.locator,
                args.description,
                args.capabilities.split()
                )
            if isinstance(oldElement, Resource) \
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
            elif isinstance(element, Resource):
                return dict(
                    restype = element['type'],
                    capabilities = ' '.join(element['capabilities']),
                    description = element['description'],
                    locator = element['locator']
                    )
            else:
                raise InvalidRequest(
                    'Resource "%s" is of a pre-defined type' % element.getId()
                    )

        def _checkState(self):
            if not self.args.restype:
                raise PresentableError(xhtml.p[
                    'No resource type was selected.'
                    ])
            resTypeName = self.args.restype
            if resTypeName not in resTypeDB:
                raise PresentableError(xhtml.p[
                    'Resource type ', xhtml.b[resTypeName],
                    ' does not exist (anymore).'
                    ])
            if resTypeName == taskRunnerResourceTypeName:
                raise PresentableError(xhtml.p[
                    'This page cannot be used to create Task Runners.'
                    ])

    def getFormContent(self, proc):
        args = proc.args
        if args.id != '':
            yield xhtml.h2[ 'Resource: ', xhtml.b[ args.id ]]
        yield vgroup[
            CustomResTypeTable.instance,
            xhtml.p[
                'If none of the listed resource types is appropriate, you can ',
                pageLink('ResTypeEdit')[ 'create a new resource type' ],'.'
                ],
            CapabilitiesPanel.instance,
            LocatorPanel.instance,
            CommentPanel.instance
            ]

class LocatorPanel(Panel):
    label = 'Locator'
    content = xhtml.br.join((
        textInput(name = 'locator', size = 80, style='width:100%'),
        'The locator is used to identify the reserved resource '
        'to the wrapper.',
        'If this resource is accessed implicitly, you can leave '
        'the locator empty.'
        ))

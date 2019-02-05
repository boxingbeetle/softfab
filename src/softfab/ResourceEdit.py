# SPDX-License-Identifier: BSD-3-Clause

from EditPage import EditPage
from Page import PresentableError
from formlib import RadioTable, textInput
from pageargs import StrArg
from resourcelib import Resource, resourceDB
from resourceview import CapabilitiesPanel, CommentPanel
from restypelib import resTypeDB, taskRunnerResourceTypeName
from restypeview import ResTypeTableMixin
from webgui import Panel, pageLink, vgroup
from xmlgen import xhtml

class CustomResTypeTable(ResTypeTableMixin, RadioTable):
    reserved = False

class ResourceEdit(EditPage):
    # FabPage constants:
    icon = 'IconResources'
    description = 'Edit Resource'
    linkDescription = 'New Resource'

    # EditPage constants:
    elemTitle = 'Resource'
    elemName = 'resource'
    db = resourceDB
    privDenyText = 'resources'
    useScript = False
    formId = 'resource'
    autoName = None

    class Arguments(EditPage.Arguments):
        restype = StrArg('')
        capabilities = StrArg('')
        locator = StrArg('')
        description = StrArg('')

    class Processor(EditPage.Processor):

        def createElement(self, req, recordId, args, oldElement):
            element = Resource.create(
                recordId,
                args.restype,
                args.locator,
                args.description,
                args.capabilities.split()
                )
            if oldElement is not None and oldElement.getId() == recordId:
                # Preserve resource state.
                # Do this only when a resource is overwritten by itself, not
                # if one resource overwrites another or if a new resource is
                # created using Save As.
                element.copyState(oldElement)
            return element

        def _initArgs(self, element):
            if element is None:
                return {}
            else:
                return dict(
                    restype = element['type'],
                    capabilities = ' '.join(element['capabilities']),
                    description = element['description'],
                    locator = element['locator']
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

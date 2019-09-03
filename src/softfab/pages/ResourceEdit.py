# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, Optional, cast

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.Page import InvalidRequest, PresentableError
from softfab.databaselib import Database
from softfab.formlib import RadioTable, textInput
from softfab.pageargs import StrArg
from softfab.resourcelib import Resource, resourceDB
from softfab.resourceview import CapabilitiesPanel, CommentPanel
from softfab.restypelib import resTypeDB, taskRunnerResourceTypeName
from softfab.restypeview import ResTypeTableMixin
from softfab.webgui import Panel, pageLink, vgroup
from softfab.xmlgen import XMLContent, xhtml


class ResourceEditArgs(EditArgs):
    restype = StrArg('')
    capabilities = StrArg('')
    locator = StrArg('')
    description = StrArg('')

class ResourceEditBase(EditPage[ResourceEditArgs, Resource]):
    # FabPage constants:
    icon = 'IconResources'
    description = 'Edit Resource'
    linkDescription = False

    # EditPage constants:
    elemTitle = 'Resource'
    elemName = 'resource'
    db = cast(Database[Resource], resourceDB)
    privDenyText = 'resources'
    useScript = False
    formId = 'resource'
    autoName = None

    def getFormContent(self,
                       proc: EditProcessorBase[ResourceEditArgs, Resource]
                       ) -> XMLContent:
        args = proc.args
        if args.id != '':
            yield xhtml.h3[ 'Resource: ', xhtml.b[ args.id ]]
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

class ResourceEdit_GET(ResourceEditBase):

    class Arguments(InitialEditArgs):
        pass

    class Processor(InitialEditProcessor[ResourceEditArgs, Resource]):
        argsClass = ResourceEditArgs

        def _initArgs(self, element: Optional[Resource]) -> Mapping[str, str]:
            if element is None:
                return {}
            elif isinstance(element, Resource):
                locator = element.getParameter('locator')
                assert locator is not None
                return dict(
                    restype=element.typeName,
                    capabilities=' '.join(element.capabilities),
                    description=element.description,
                    locator=locator
                    )
            else:
                raise InvalidRequest(
                    f'Resource "{element.getId()}" is of a pre-defined type'
                    )

class ResourceEdit_POST(ResourceEditBase):

    class Arguments(ResourceEditArgs):
        pass

    class Processor(EditProcessor[ResourceEditArgs, Resource]):

        def createElement(self,
                          recordId: str,
                          args: ResourceEditArgs,
                          oldElement: Optional[Resource]
                          ) -> Resource:
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

        def _checkState(self) -> None:
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

class CustomResTypeTable(ResTypeTableMixin, RadioTable):
    reserved = False

class LocatorPanel(Panel):
    label = 'Locator'
    content = xhtml.br.join((
        textInput(name = 'locator', size = 80, style='width:100%'),
        'The locator is used to identify the reserved resource '
        'to the wrapper.',
        'If this resource is accessed implicitly, you can leave '
        'the locator empty.'
        ))

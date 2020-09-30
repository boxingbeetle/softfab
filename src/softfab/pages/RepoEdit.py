# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Mapping, Optional

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.Page import InvalidRequest
from softfab.formlib import textInput
from softfab.pageargs import PasswordArg, StrArg
from softfab.resourcelib import Resource, ResourceDB
from softfab.resourceview import CommentPanel
from softfab.restypelib import repoResourceTypeName
from softfab.webgui import Panel, vgroup
from softfab.xmlgen import XMLContent, xhtml


class RepoEditArgs(EditArgs):
    locator = StrArg('')
    secret = PasswordArg()
    capabilities = StrArg('')
    description = StrArg('')

class RepoEditBase(EditPage[RepoEditArgs, Resource]):
    # FabPage constants:
    icon = 'IconResources'
    description = 'Edit Repository'
    linkDescription = False

    # EditPage constants:
    elemTitle = 'Repository'
    elemName = 'repository'
    dbName = 'resourceDB'
    privDenyText = 'repositories'
    useScript = False
    formId = 'repo'
    autoName = None

    def getFormContent(self, proc: EditProcessorBase) -> XMLContent:
        args = proc.args
        if args.id != '':
            yield xhtml.h3[ 'Repository: ', xhtml.b[ args.id ]]
        yield vgroup[
            LocatorPanel.instance,
            SecretPanel.instance,
            CapabilitiesPanel.instance,
            CommentPanel.instance,
            ]

class RepoEdit_GET(RepoEditBase):

    class Arguments(InitialEditArgs):
        pass

    class Processor(InitialEditProcessor[RepoEditArgs, Resource]):
        argsClass = RepoEditArgs

        resourceDB: ClassVar[ResourceDB]

        def _initArgs(self,
                      element: Optional[Resource]
                      ) -> Mapping[str, object]:
            if element is None:
                return dict(secret='')
            elif element.typeName == repoResourceTypeName:
                return dict(
                    locator = element.getParameter('locator') or '',
                    secret = element.getParameter('secret') or '',
                    capabilities = ' '.join(element.capabilities),
                    description = element['description']
                    )
            else:
                raise InvalidRequest(
                    f'Resource "{element.getId()}" is not a repository'
                    )

class RepoEdit_POST(RepoEditBase):

    class Arguments(RepoEditArgs):
        pass

    class Processor(EditProcessor[RepoEditArgs, Resource]):

        resourceDB: ClassVar[ResourceDB]

        def createElement(self,
                          recordId: str,
                          args: RepoEditArgs,
                          oldElement: Optional[Resource]
                          ) -> Resource:
            resourceFactory = self.resourceDB.factory
            resource = resourceFactory.newResource(
                recordId,
                repoResourceTypeName,
                args.description,
                args.capabilities.split()
                )
            resource.addParameter('locator', args.locator)
            secret = args.secret
            if secret:
                resource.addParameter('secret', secret)
            if oldElement is not None and oldElement.getId() == recordId:
                # Preserve resource state.
                # Do this only when a resource is overwritten by itself, not
                # if one resource overwrites another or if a new resource is
                # created using Save As.
                resource.copyState(oldElement)
            return resource

class LocatorPanel(Panel):
    label = 'Locator'
    content = xhtml[
        textInput(name='locator', size=80, style='width:100%'),
        xhtml.p[
            "The locator, typically a URL, tells the version control system "
            "where it can find the repository."
            ]
        ]

class SecretPanel(Panel):
    label = 'Secret'
    content = xhtml[
        textInput(name='secret', size=80, style='width:100%',
                  class_='obfuscate', autocomplete='off'),
        xhtml.p[
            "Webhooks can be used to report changes in this repository. "
            "The same secret must be entered here and on the site hosting the "
            "repository. "
            "If no secret is entered here, webhooks will be inactive for this "
            "repository."
            ]
        ]

class CapabilitiesPanel(Panel):
    label = 'Capabilities'
    content = xhtml[
        textInput(name='capabilities', size=80, style='width:100%'),
        xhtml.p[
            "Multiple capabilities should be separated by spaces."
            ],
        xhtml.p[
            "It is recommended to use a capability to specify the content "
            "of the repository, for example ", xhtml.code['killerapp'], ", ",
            xhtml.code['libfoo'], " or ", xhtml.code['website'], ". ",
            "Task definitions can then use that capability to request "
            "the repository they need."
            ]
        ]

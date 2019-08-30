# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, Optional, cast

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.Page import InvalidRequest
from softfab.databaselib import Database
from softfab.formlib import textInput
from softfab.pageargs import StrArg
from softfab.resourcelib import Resource, resourceDB
from softfab.resourceview import CommentPanel
from softfab.restypelib import repoResourceTypeName
from softfab.webgui import Panel, vgroup
from softfab.xmlgen import XMLContent, xhtml


class RepoEditArgs(EditArgs):
    locator = StrArg('')
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
    db = cast(Database[Resource], resourceDB)
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
            CapabilitiesPanel.instance,
            CommentPanel.instance,
            ]

class RepoEdit_GET(RepoEditBase):

    class Arguments(InitialEditArgs):
        pass

    class Processor(InitialEditProcessor[RepoEditArgs, Resource]):
        argsClass = RepoEditArgs

        def _initArgs(self,
                      element: Optional[Resource]
                      ) -> Mapping[str, object]:
            if element is None:
                return {}
            elif element.typeName == repoResourceTypeName:
                return dict(
                    locator = element.locator,
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

        def createElement(self,
                          recordId: str,
                          args: RepoEditArgs,
                          oldElement: Optional[Resource]
                          ) -> Resource:
            return Resource.create(
                recordId,
                repoResourceTypeName,
                args.locator,
                args.description,
                args.capabilities.split()
                )

class LocatorPanel(Panel):
    label = 'Locator'
    content = xhtml.br.join((
        textInput(name='locator', size=80, style='width:100%'),
        'The locator, typically a URL, tells the version control system '
        'where it can find the repository.'
        ))

class CapabilitiesPanel(Panel):
    label = 'Capabilities'
    content = xhtml.br.join((
        textInput(name='capabilities', size=80, style='width:100%'),
        'Multiple capabilities should be separated by spaces.',
        ('It is recommended to use a capability to specify the content '
         'of the repository, for example ', xhtml.code['killerapp'], ', ',
         xhtml.code['libfoo'], ' or ', xhtml.code['website'], '. ',
         'Task definitions can then use that capability to request '
         'the repository they need.'
         )
        ))

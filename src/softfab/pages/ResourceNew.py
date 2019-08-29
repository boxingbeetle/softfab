# SPDX-License-Identifier: BSD-3-Clause

from typing import Sequence, Tuple

from softfab.FabPage import FabPage, IconModifier
from softfab.restypelib import resTypeDB, taskRunnerResourceTypeName
from softfab.userlib import User, checkPrivilege
from softfab.webgui import pageLink
from softfab.xmlgen import XMLContent, xhtml


taskRunnerType = resTypeDB[taskRunnerResourceTypeName]

class ResourceNew_GET(FabPage[FabPage.Processor, FabPage.Arguments]):
    icon = 'IconResources'
    iconModifier = IconModifier.NEW
    description = 'New Resource'

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'rt/l')

    def presentContent(self, **kwargs: object) -> XMLContent:
        descriptions = (
            ( pageLink('TaskRunnerEdit')[taskRunnerType.presentationName],
                f'{taskRunnerType.description}.'
                ),
            ( pageLink('ResourceEdit')['Custom'],
                'A user-defined resource type.'
                ),
            ) # type: Sequence[Tuple[XMLContent, XMLContent]]

        yield xhtml.p['Choose the type of resource you want to create:']
        yield xhtml.dl(class_='toc')[(
            ( xhtml.dt[name], xhtml.dd[descr] ) for name, descr in descriptions
            )]

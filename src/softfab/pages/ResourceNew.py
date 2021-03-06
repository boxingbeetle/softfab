# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, Tuple

from softfab.FabPage import FabPage, IconModifier
from softfab.restypelib import (
    presentResTypeName, reservedResourceTypeDescriptions
)
from softfab.restypeview import reservedTypes
from softfab.users import User, checkPrivilege
from softfab.webgui import pageLink
from softfab.xmlgen import XMLContent, xhtml


class ResourceNew_GET(FabPage[FabPage.Processor, FabPage.Arguments]):
    icon = 'IconResources'
    iconModifier = IconModifier.NEW
    description = 'New Resource'

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'rt/l')

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield xhtml.p['Choose the type of resource you want to create:']
        yield xhtml.dl(class_='toc')[(
            (xhtml.dt[name], xhtml.dd[descr])
            for name, descr in self.iterOptions()
            )]

    def iterOptions(self) -> Iterator[Tuple[XMLContent, XMLContent]]:
        for resType in reservedTypes:
            name = resType.name
            yield (
                pageLink(resType.editPage)[
                    presentResTypeName(name)
                    ],
                f'{reservedResourceTypeDescriptions[name]}.'
                )
        yield (
            pageLink('ResourceEdit')['Custom'],
            'A user-defined resource type.'
            )

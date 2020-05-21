# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, Tuple

import attr

from softfab.pagelinks import CapFilterArgs, pageLink
from softfab.restypelib import (
    ResType, presentResTypeName, repoResourceTypeName, resTypeDB,
    taskRunnerResourceTypeName
)
from softfab.webgui import Column
from softfab.xmlgen import XMLContent, XMLNode


def createCapabilityLink(typeName: str, cap: str = '') -> XMLNode:
    return pageLink('Capabilities', CapFilterArgs(restype=typeName, cap=cap))[
        cap or presentResTypeName(typeName)
        ]

def createTargetLink(target: str) -> XMLNode:
    return createCapabilityLink(taskRunnerResourceTypeName, target)

@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class ResourceTypeInfo:
    name: str
    editPage: str

    @property
    def record(self) -> ResType:
        return resTypeDB[self.name]

reservedTypes = (
    ResourceTypeInfo(
        name=taskRunnerResourceTypeName,
        editPage='TaskRunnerEdit'
        ),
    ResourceTypeInfo(
        name=repoResourceTypeName,
        editPage='RepoEdit'
        ),
    )

def iterResourceTypes(reserved: bool = True) -> Iterator[ResType]:
    """The resource types in this factory, in presentation order.
    """
    if reserved:
        for resType in reservedTypes:
            yield resType.record
    for recordId in sorted(recordId
                           for recordId in resTypeDB.keys()
                           if not recordId.startswith('sf.')):
        yield resTypeDB[recordId]

class DescriptionColumn(Column):
    label = 'Description'

    def presentHeader(self, **kwargs: object) -> XMLNode:
        return super().presentHeader(**kwargs)(style='width:62%')

class ResTypeTableMixin:
    name = 'restype'
    columns = 'Resource Type', DescriptionColumn.instance
    reserved = True

    def iterOptions(self,
                    **_kwargs: object
                    ) -> Iterator[Tuple[str, XMLContent, XMLContent]]:
        for resType in iterResourceTypes(self.reserved):
            name = resType.getId()
            yield name, presentResTypeName(name), resType.description

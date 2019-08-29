# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, Tuple

import attr

from softfab.restypelib import ResType, resTypeDB, taskRunnerResourceTypeName
from softfab.webgui import Column
from softfab.xmlgen import XMLContent, XMLNode


@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class ResourceTypeInfo:
    name: str
    editPage: str
    record: ResType = attr.ib(init=False)
    def __attrs_post_init__(self):
        object.__setattr__(self, 'record', resTypeDB[self.name])

reservedTypes = (
    ResourceTypeInfo(
        name=taskRunnerResourceTypeName,
        editPage='TaskRunnerEdit'
        ),
    )

def iterResourceTypes(reserved: bool) -> Iterator[ResType]:
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
            yield resType.getId(), resType.presentationName, resType.description

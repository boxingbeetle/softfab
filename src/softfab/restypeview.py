# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, Tuple

from softfab.restypelib import resTypeDB, taskRunnerResourceTypeName
from softfab.webgui import Column
from softfab.xmlgen import XMLContent, XMLNode


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
        resTypeNames = sorted(resTypeDB.keys())
        resTypeNames.remove(taskRunnerResourceTypeName)
        if self.reserved:
            resTypeNames.insert(0, taskRunnerResourceTypeName)
        for name in resTypeNames:
            resType = resTypeDB[name]
            yield name, resType.presentationName, resType.description

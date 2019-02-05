# SPDX-License-Identifier: BSD-3-Clause

from restypelib import resTypeDB, taskRunnerResourceTypeName
from webgui import Column

class DescriptionColumn(Column):
    label = 'Description'

    def presentHeader(self, **kwargs):
        return super().presentHeader(**kwargs)(style='width:62%')

class ResTypeTableMixin:
    name = 'restype'
    columns = 'Resource Type', DescriptionColumn.instance
    reserved = True

    def iterOptions(self, **kwargs):
        resTypeNames = sorted(resTypeDB.keys())
        resTypeNames.remove(taskRunnerResourceTypeName)
        if self.reserved:
            resTypeNames.insert(0, taskRunnerResourceTypeName)
        for name in resTypeNames:
            resType = resTypeDB[name]
            yield name, resType['presentation'], resType.getDescription()

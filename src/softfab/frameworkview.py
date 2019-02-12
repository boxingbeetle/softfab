# SPDX-License-Identifier: BSD-3-Clause

from softfab.datawidgets import DataColumn
from softfab.pagelinks import createFrameworkDetailsLink
from softfab.taskdeflib import taskDefDB

class FrameworkColumn(DataColumn):
    def presentCell(self, record, **kwargs):
        return createFrameworkDetailsLink(record[self.keyName])

def taskDefsUsingFramework(frameworkId):
    '''Iterates through the IDs of those task definitions that inherit from
    the framework with the given ID.
    '''
    for taskId, taskDef in taskDefDB.items():
        if taskDef['parent'] == frameworkId:
            yield taskId

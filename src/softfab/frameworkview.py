# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, cast

from softfab.datawidgets import DataColumn
from softfab.frameworklib import TaskDefBase
from softfab.pagelinks import createFrameworkDetailsLink
from softfab.taskdeflib import taskDefDB
from softfab.xmlgen import XMLContent


class FrameworkColumn(DataColumn[TaskDefBase]):
    def presentCell(self, record: TaskDefBase, **kwargs: object) -> XMLContent:
        key = self.keyName
        assert key is not None
        return createFrameworkDetailsLink(cast(str, record[key]))

def taskDefsUsingFramework(frameworkId: str) -> Iterator[str]:
    '''Iterates through the IDs of those task definitions that inherit from
    the framework with the given ID.
    '''
    for taskId, taskDef in taskDefDB.items():
        if taskDef['parent'] == frameworkId:
            yield taskId

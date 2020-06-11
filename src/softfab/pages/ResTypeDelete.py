# SPDX-License-Identifier: BSD-3-Clause

from typing import Callable, ClassVar, TypeVar

from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
)
from softfab.databaselib import Database
from softfab.frameworklib import FrameworkDB, TaskDefBase
from softfab.pageargs import RefererArg
from softfab.pagelinks import createFrameworkDetailsLink, createTaskDetailsLink
from softfab.resourcelib import ResourceDB
from softfab.restypelib import ResType, ResTypeDB
from softfab.taskdeflib import TaskDefDB
from softfab.xmlgen import XMLContent

TaskDefT = TypeVar('TaskDefT', bound=TaskDefBase)

def checkRequirements(db: Database[TaskDefT],
                      typeName: str,
                      linkFunc: Callable[[str], XMLContent]
                      ) -> None:
    usedBy = {
        record.getId()
        for record in db
        if list(record.resourceClaim.iterSpecsOfType(typeName))
        }
    if usedBy:
        raise RecordInUseError(db.description, linkFunc, usedBy)

class ResTypeDelete_GET(RecordDelete_GET):
    description = 'Delete Resource Type'
    icon = 'IconResources'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('ResTypeIndex')

    class Processor(RecordDelete_GET.Processor[ResType]):
        frameworkDB: ClassVar[FrameworkDB]
        resTypeDB: ClassVar[ResTypeDB]
        resourceDB: ClassVar[ResourceDB]
        taskDefDB: ClassVar[TaskDefDB]
        recordName = 'resource type'
        denyText = 'resource types'

        @property
        def db(self) -> ResTypeDB:
            return self.resTypeDB

        def checkState(self, record: ResType) ->  None:
            name = record.getId()

            # Check for resources of this type.
            resourcesIds = self.resourceDB.resourcesOfType(name)
            if resourcesIds:
                # Note: There is currently no details page for resources,
                #       so we present just the name.
                raise RecordInUseError(
                    'resource', lambda resourceId: resourceId, resourcesIds
                    )

            # Check for resource requirements of this type.
            checkRequirements(self.frameworkDB, name,
                              createFrameworkDetailsLink)
            checkRequirements(self.taskDefDB, name,
                              createTaskDetailsLink)

class ResTypeDelete_POST(RecordDelete_POSTMixin, ResTypeDelete_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    ResTypeDelete_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    ResTypeDelete_GET.Processor):
        pass

# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import PageProcessor
from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
)
from softfab.frameworklib import frameworkDB
from softfab.pageargs import RefererArg
from softfab.pagelinks import createFrameworkDetailsLink, createTaskDetailsLink
from softfab.resourcelib import resourceDB
from softfab.restypelib import ResType, resTypeDB
from softfab.taskdeflib import taskDefDB


def checkRequirements(db, typeName, linkFunc):
    usedBy = {
        record.getId()
        for record in db
        if list(record.resourceClaim.iterSpecsOfType(typeName))
        }
    if usedBy:
        raise RecordInUseError(db.description, linkFunc, usedBy)

class ResTypeDelete_GET(RecordDelete_GET):
    db = resTypeDB
    recordName = 'resource type'
    denyText = 'resource types'

    description = 'Delete Resource Type'
    icon = 'IconResources'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('ResTypeIndex')

    def checkState(self, record: ResType) ->  None:
        name = record.getId()

        # Check for resources of this type.
        resourcesIds = resourceDB.resourcesOfType(name)
        if resourcesIds:
            # Note: There is currently no details page for resources,
            #       so we present just the name.
            raise RecordInUseError(
                'resource', lambda resourceId: resourceId, resourcesIds
                )

        # Check for resource requirements of this type.
        checkRequirements(frameworkDB, name, createFrameworkDetailsLink)
        checkRequirements(taskDefDB, name, createTaskDetailsLink)

class ResTypeDelete_POST(RecordDelete_POSTMixin, ResTypeDelete_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    ResTypeDelete_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    PageProcessor['ResTypeDelete_POST.Arguments']):
        pass

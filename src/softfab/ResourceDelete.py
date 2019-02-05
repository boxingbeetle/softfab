# SPDX-License-Identifier: BSD-3-Clause

from RecordDelete import RecordDelete_GET, RecordDelete_POSTMixin
from pageargs import RefererArg
from resourcelib import resourceDB

class ParentArgs:
    indexQuery = RefererArg('ResourceIndex')

class ResourceDelete_GET(RecordDelete_GET):
    db = resourceDB
    recordName = 'resource'
    denyText = 'resources'

    description = 'Delete Resource'
    icon = 'IconResources'

    class Arguments(RecordDelete_GET.Arguments, ParentArgs):
        pass

class ResourceDelete_POST(RecordDelete_POSTMixin, ResourceDelete_GET):

    class Arguments(RecordDelete_POSTMixin.Arguments, ParentArgs):
        pass

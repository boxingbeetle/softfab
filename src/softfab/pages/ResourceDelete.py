# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import PageProcessor
from softfab.RecordDelete import RecordDelete_GET, RecordDelete_POSTMixin
from softfab.pageargs import RefererArg
from softfab.resourcelib import resourceDB


class ResourceDelete_GET(RecordDelete_GET):
    db = resourceDB
    recordName = 'resource'
    denyText = 'resources'

    description = 'Delete Resource'
    icon = 'IconResources'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('ResourceIndex')

class ResourceDelete_POST(RecordDelete_POSTMixin, ResourceDelete_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    ResourceDelete_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    PageProcessor['ResourceDelete_POST.Arguments']):
        pass

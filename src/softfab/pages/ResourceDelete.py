# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar

from softfab.RecordDelete import RecordDelete_GET, RecordDelete_POSTMixin
from softfab.pageargs import RefererArg
from softfab.resourcelib import ResourceBase, ResourceDB


class ResourceDelete_GET(RecordDelete_GET):
    description = 'Delete Resource'
    icon = 'IconResources'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('ResourceIndex')

    class Processor(RecordDelete_GET.Processor[ResourceBase]):
        resourceDB: ClassVar[ResourceDB]
        recordName = 'resource'
        denyText = 'resources'

        @property
        def db(self) -> ResourceDB:
            return self.resourceDB

class ResourceDelete_POST(RecordDelete_POSTMixin, ResourceDelete_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    ResourceDelete_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    ResourceDelete_GET.Processor):
        pass

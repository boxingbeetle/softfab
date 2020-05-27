# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar

from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
)
from softfab.frameworklib import FrameworkDB
from softfab.pageargs import RefererArg
from softfab.pagelinks import createFrameworkDetailsLink
from softfab.productdeflib import ProductDef, ProductDefDB


class ProductDelete_GET(RecordDelete_GET):
    description = 'Delete Product'
    icon = 'Product1'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('ProductIndex')
        detailsQuery = RefererArg('ProductDetails')

    class Processor(RecordDelete_GET.Processor[ProductDef]):
        productDefDB: ClassVar[ProductDefDB]
        frameworkDB: ClassVar[FrameworkDB]
        recordName = 'product'
        denyText = 'product definitions'

        @property
        def db(self) -> ProductDefDB:
            return self.productDefDB

        def checkState(self, record: ProductDef) -> None:
            # TODO: The following code partially duplicates FrameworkDelete
            name = record.getId()
            frameworksIds = [
                frameworkId
                for frameworkId, framework in self.frameworkDB.items()
                if name in framework.getInputs() or
                   name in framework.getOutputs()
                ]
            if frameworksIds:
                raise RecordInUseError(
                    'framework', createFrameworkDetailsLink, frameworksIds
                    )

class ProductDelete_POST(RecordDelete_POSTMixin, ProductDelete_GET):

    class Arguments(RecordDelete_POSTMixin.ArgumentsMixin,
                    ProductDelete_GET.Arguments):
        pass

    class Processor(RecordDelete_POSTMixin.ProcessorMixin,
                    ProductDelete_GET.Processor):
        pass

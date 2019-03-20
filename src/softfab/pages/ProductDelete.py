# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import PageProcessor
from softfab.RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
)
from softfab.frameworklib import frameworkDB
from softfab.pageargs import RefererArg
from softfab.pagelinks import createFrameworkDetailsLink
from softfab.productdeflib import productDefDB


class ProductDelete_GET(RecordDelete_GET):
    db = productDefDB
    recordName = 'product'
    denyText = 'product definitions'

    description = 'Delete Product'
    icon = 'Product1'

    class Arguments(RecordDelete_GET.Arguments):
        indexQuery = RefererArg('ProductIndex')
        detailsQuery = RefererArg('ProductDetails')

    def checkState(self, record):
        # TODO: The following code partially duplicates FrameworkDelete
        name = record.getId()
        frameworksIds = [
            frameworkId
            for frameworkId, framework in frameworkDB.items()
            if name in framework.getInputs() or name in framework.getOutputs()
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
                    PageProcessor['ProductDelete_POST.Arguments']):
        pass

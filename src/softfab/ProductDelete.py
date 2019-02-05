# SPDX-License-Identifier: BSD-3-Clause

from RecordDelete import (
    RecordDelete_GET, RecordDelete_POSTMixin, RecordInUseError
    )
from frameworklib import frameworkDB
from pageargs import RefererArg
from pagelinks import createFrameworkDetailsLink
from productdeflib import productDefDB

class ParentArgs:
    indexQuery = RefererArg('ProductIndex')
    detailsQuery = RefererArg('ProductDetails')

class ProductDelete_GET(RecordDelete_GET):
    db = productDefDB
    recordName = 'product'
    denyText = 'product definitions'

    description = 'Delete Product'
    icon = 'Product1'

    class Arguments(RecordDelete_GET.Arguments, ParentArgs):
        pass

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

    class Arguments(RecordDelete_POSTMixin.Arguments, ParentArgs):
        pass

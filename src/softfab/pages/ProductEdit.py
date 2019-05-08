# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, Optional

from softfab.EditPage import EditArgs, EditPage, EditProcessor
from softfab.formlib import checkBox, dropDownList
from softfab.pageargs import BoolArg, EnumArg
from softfab.productdeflib import ProductDef, ProductType, productDefDB
from softfab.request import Request
from softfab.webgui import PropertiesTable, docLink


class ProductEdit(EditPage):
    # FabPage constants:
    icon = 'Product1'
    description = 'Edit Product'
    linkDescription = 'New Product'

    # EditPage constants:
    elemTitle = 'Product'
    elemName = 'product'
    db = productDefDB
    privDenyText = 'product definitions'
    useScript = False
    formId = 'product'
    autoName = None

    class Arguments(EditArgs):
        type = EnumArg(ProductType, ProductType.STRING)
        local = BoolArg()
        combined = BoolArg()

    class Processor(EditProcessor['ProductEdit.Arguments', ProductDef]):

        def createElement(self,
                          recordId: str,
                          args: 'ProductEdit.Arguments',
                          oldElement: Optional[ProductDef]
                          ) -> ProductDef:
            return ProductDef.create(
                recordId, args.type, args.local, args.combined
                )

        def _initArgs(self,
                      element: Optional[ProductDef]
                      ) -> Mapping[str, object]:
            if element is None:
                return {}
            else:
                return dict(
                    type = element['type'],
                    local = element.isLocal(),
                    combined = element.isCombined()
                    )

    def getFormContent(self, proc):
        return ProductTable.instance

class ProductTable(PropertiesTable):

    def iterRows(self, *, proc, **kwargs):
        yield 'Product ID', proc.args.id or '(untitled)'
        yield 'Locator type', dropDownList(name='type')[ ProductType ]
        yield 'Local', (
            checkBox(name='local')[
                'Product is only accessible to the Task Runner that created it'
                ],
            ' (',
            docLink('/introduction/execution-graph/#local_product')[
                'documentation'
                ],
            ')'
            )
        yield 'Combined', (
            checkBox(name='combined')[
                'Product is the combination of outputs from multiple tasks'
                ],
            ' (',
            docLink('/introduction/execution-graph/#combined_product')[
                'documentation'
                ],
            ')'
            )

# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Iterator, Mapping, Optional, cast

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.formlib import checkBox, dropDownList
from softfab.pageargs import BoolArg, EnumArg
from softfab.productdeflib import ProductDef, ProductDefDB, ProductType
from softfab.webgui import PropertiesTable, docLink
from softfab.xmlgen import XMLContent


class ProductEditArgs(EditArgs):
    type = EnumArg(ProductType, ProductType.STRING)
    local = BoolArg()
    combined = BoolArg()

class ProductEditBase(EditPage[ProductEditArgs, ProductDef]):
    # FabPage constants:
    icon = 'Product1'
    description = 'Edit Product'
    linkDescription = 'New Product'

    # EditPage constants:
    elemTitle = 'Product'
    elemName = 'product'
    dbName = 'productDefDB'
    privDenyText = 'product definitions'
    useScript = False
    formId = 'product'
    autoName = None

    def getFormContent(self,
                       proc: EditProcessorBase[ProductEditArgs, ProductDef]
                       ) -> XMLContent:
        return ProductTable.instance

class ProductEdit_GET(ProductEditBase):

    class Arguments(InitialEditArgs):
        pass

    class Processor(InitialEditProcessor[ProductEditArgs, ProductDef]):
        argsClass = ProductEditArgs

        productDefDB: ClassVar[ProductDefDB]

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

class ProductEdit_POST(ProductEditBase):

    class Arguments(ProductEditArgs):
        pass

    class Processor(EditProcessor[Arguments, ProductDef]):

        productDefDB: ClassVar[ProductDefDB]

        def createElement(self,
                          recordId: str,
                          args: ProductEditArgs,
                          oldElement: Optional[ProductDef]
                          ) -> ProductDef:
            return ProductDef.create(
                recordId, args.type, args.local, args.combined
                )

class ProductTable(PropertiesTable):

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(EditProcessorBase[ProductEditArgs, ProductDef],
                    kwargs['proc'])
        yield 'Product ID', proc.args.id or '(untitled)'
        yield 'Locator type', dropDownList(name='type')[ ProductType ]
        yield 'Local', (
            checkBox(name='local')[
                'Product is only accessible to the Task Runner that created it'
                ],
            ' (',
            docLink('/concepts/exegraph/#local_product')[
                'documentation'
                ],
            ')'
            )
        yield 'Combined', (
            checkBox(name='combined')[
                'Product is the combination of outputs from multiple tasks'
                ],
            ' (',
            docLink('/concepts/exegraph/#combined_product')[
                'documentation'
                ],
            ')'
            )

# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import Mapping, cast

from softfab.config import dbDir
from softfab.databaselib import (
    DatabaseElem, VersionedDatabase, checkWrapperVarName
)
from softfab.xmlbind import XMLAttributeValue, XMLTag


class ProductFactory:
    @staticmethod
    def createProduct(attributes: Mapping[str, str]) -> 'ProductDef':
        return ProductDef(attributes)

class ProductDefDB(VersionedDatabase['ProductDef']):
    factory = ProductFactory()
    privilegeObject = 'pd'
    description = 'product definition'
    uniqueKeys = ( 'id', )

    def _customCheckId(self, key: str) -> None:
        checkWrapperVarName(key)

productDefDB = ProductDefDB(dbDir / 'productdefs')

class ProductType(Enum):
    """Available product locator types.

    The first element is the default type.
    """
    STRING = 1
    URL = 2
    TOKEN = 3

class ProductDef(XMLTag, DatabaseElem):
    tagName = 'product'
    boolProperties = ('local', 'combined')
    enumProperties = {'type': ProductType}

    @classmethod
    def create(cls,
               name: str,
               prodType: ProductType = ProductType.STRING,
               local: bool = False,
               combined: bool = False
               ) -> 'ProductDef':
        return cls(dict(
            id = name,
            type = prodType.name.lower(),
            local = local,
            combined = combined,
            ))

    def __init__(self, properties: Mapping[str, XMLAttributeValue]):
        # COMPAT 2.16: Product type "file" no longer exists, but it behaved
        #              as "string" during execution, so map it to that.
        if properties.get('type') == 'file':
            properties = dict(properties, type='string')

        super().__init__(properties)

    def getId(self) -> str:
        return cast(str, self['id'])

    def getType(self) -> ProductType:
        return cast(ProductType, self['type'])

    def isLocal(self) -> bool:
        return cast(bool, self['local'])

    def isCombined(self) -> bool:
        return cast(bool, self['combined'])

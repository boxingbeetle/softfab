# SPDX-License-Identifier: BSD-3-Clause

from softfab.config import dbDir
from softfab.databaselib import (
    DatabaseElem, VersionedDatabase, checkWrapperVarName
    )
from softfab.xmlbind import XMLTag

from enum import Enum

class ProductFactory:
    @staticmethod
    def createProduct(attributes):
        return ProductDef(attributes)

class ProductDefDB(VersionedDatabase):
    baseDir = dbDir + '/productdefs'
    factory = ProductFactory()
    privilegeObject = 'pd'
    description = 'product definition'
    uniqueKeys = ( 'id', )

    def _customCheckId(self, key):
        checkWrapperVarName(key)

productDefDB = ProductDefDB()

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
    def create(
        cls, name, prodType=ProductType.STRING, local=False, combined=False
        ):
        properties = dict(
            id = name,
            type = prodType.name.lower(),
            local = local,
            combined = combined,
            )
        return cls(properties)

    def __init__(self, properties):
        # COMPAT 2.16: Product type "file" no longer exists, but it behaved
        #              as "string" during execution, so map it to that.
        if properties.get('type') == 'file':
            properties = dict(properties, type='string')

        XMLTag.__init__(self, properties)
        DatabaseElem.__init__(self)

    def getId(self):
        return self['id']

    def isLocal(self):
        return self['local']

    def isCombined(self):
        return self['combined']

# SPDX-License-Identifier: BSD-3-Clause

from functools import total_ordering
from typing import Dict, Iterator, Mapping, Optional, Tuple, cast

from softfab.config import dbDir
from softfab.databaselib import Database, DatabaseElem, createInternalId
from softfab.productdeflib import ProductDef, ProductType, productDefDB
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLContent, xml


class ProductFactory:
    @staticmethod
    def createProduct(attributes: Mapping[str, str]) -> 'Product':
        return Product(attributes)

class ProductDB(Database['Product']):
    factory = ProductFactory()
    privilegeObject = 'j' # every product is a part of a job
    description = 'product'
    uniqueKeys = ( 'id', )
    alwaysInMemory = False

productDB = ProductDB(dbDir + '/products')

@total_ordering
class Product(XMLTag, DatabaseElem):
    tagName = 'product'

    @classmethod
    def create(cls, name: str) -> 'Product':
        product = cls(dict(
            id = createInternalId(),
            name = name,
            state = 'waiting',
            pdKey = productDefDB.latestVersion(name)
            ))
        productDB.add(product)
        return product

    def __init__(self, attributes: Mapping[str, Optional[str]]):
        super().__init__(attributes)
        self.__producers: Dict[str, str] = {}

    def __hash__(self) -> int:
        return hash(self.getName())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Product):
            return self.getName() == other.getName()
        else:
            return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Product):
            return self.getName() < other.getName()
        else:
            return NotImplemented

    def _addProducer(self, attributes: Mapping[str, str]) -> None:
        self.__producers[attributes['taskId']] = attributes['locator']

    def _getContent(self) -> XMLContent:
        for taskId, locator in self.__producers.items():
            yield xml.producer(taskId = taskId, locator = locator)

    def getId(self) -> str:
        return cast(str, self._properties['id'])

    def getName(self) -> str:
        return cast(str, self._properties['name'])

    def getDef(self) -> ProductDef:
        return productDefDB.getVersion(cast(str, self._properties['pdKey']))

    def getType(self) -> ProductType:
        return cast(ProductType, self.getDef()['type'])

    def isLocal(self) -> bool:
        return self.getDef().isLocal()

    def isCombined(self) -> bool:
        return self.getDef().isCombined()

    def getLocalAt(self) -> Optional[str]:
        return cast(Optional[str], self._properties.get('localAt'))

    def getLocator(self, taskName: Optional[str] = None) -> Optional[str]:
        '''Gets the locator for this product, or None if there isn't one.
        If a task name is provided, the locator produced by that particular
        task is returned, otherwise the first reported locator is returned.
        '''
        if taskName is None:
            return cast(Optional[str], self._properties.get('locator'))
        else:
            return self.__producers.get(taskName)

    def getProducers(self) -> Iterator[Tuple[str, str]]:
        '''Returns an iterator which contains the producers of a product.
        Only the tasks that have reported a locator are included.
        The iterator contains pairs of task name and locator.
        '''
        return iter(self.__producers.items())

    def isAvailable(self) -> bool:
        return self._properties['state'] == 'done'

    def isBlocked(self) -> bool:
        return self._properties['state'] == 'blocked'

    def setLocalAt(self, taskRunnerId: str) -> None:
        '''Binds this product to the given Task Runner.
        Only valid for local products.
        '''
        assert self.isLocal()
        assert taskRunnerId is not None
        prevRunnerId = self._properties.get('localAt')
        if prevRunnerId is None:
            self._properties['localAt'] = taskRunnerId
            self._notify()
        else:
            assert prevRunnerId == taskRunnerId

    def storeLocator(self, locator: str, taskName: str) -> None:
        '''Remembers a locator and the task that produced it.
        If later another locator is given for the same task, it will be ignored.
        '''
        changed = False
        if self.getType() is ProductType.TOKEN:
            # TODO: It would be better to not store a locator at all for token
            #       products, but that requires a bigger redesign than I want
            #       to perform right now.
            locator = 'token'
        if 'locator' not in self._properties:
            self._properties['locator'] = locator
            changed = True
        if taskName not in self.__producers:
            self.__producers[taskName] = locator
            changed = True
        if changed:
            self._notify()

    def done(self) -> None:
        if self._properties['state'] == 'waiting':
            self._properties['state'] = 'done'
            self._notify()

    def blocked(self) -> None:
        if self._properties['state'] == 'waiting':
            self._properties['state'] = 'blocked'
            self._notify()

# SPDX-License-Identifier: BSD-3-Clause

from functools import total_ordering

from softfab.config import dbDir
from softfab.databaselib import Database, DatabaseElem, createInternalId
from softfab.productdeflib import ProductType, productDefDB
from softfab.xmlbind import XMLTag
from softfab.xmlgen import xml

class ProductFactory:
    @staticmethod
    def createProduct(attributes):
        return Product(attributes)

class ProductDB(Database):
    baseDir = dbDir + '/products'
    factory = ProductFactory()
    privilegeObject = 'j' # every product is a part of a job
    description = 'product'
    uniqueKeys = ( 'id', )
    alwaysInMemory = False
productDB = ProductDB()

@total_ordering
class Product(XMLTag, DatabaseElem):
    tagName = 'product'

    @classmethod
    def create(cls, name):
        product = cls(dict(
            id = createInternalId(),
            name = name,
            state = 'waiting',
            pdKey = productDefDB.latestVersion(name)
            ))
        productDB.add(product)
        return product

    def __init__(self, attributes):
        XMLTag.__init__(self, attributes)
        DatabaseElem.__init__(self)
        self.__producers = {}

    def __hash__(self):
        return hash(self.getName())

    def __eq__(self, other):
        if isinstance(other, Product):
            return self.getName() == other.getName()
        else:
            return NotImplemented

    def __lt__(self, other):
        if isinstance(other, Product):
            return self.getName() < other.getName()
        else:
            return NotImplemented

    def _addProducer(self, attributes):
        self.__producers[attributes['taskId']] = attributes['locator']

    def _getContent(self):
        for taskId, locator in self.__producers.items():
            yield xml.producer(taskId = taskId, locator = locator)

    def getId(self):
        return self._properties['id']

    def getName(self):
        return self._properties['name']

    def getDef(self):
        return productDefDB.getVersion(self._properties['pdKey'])

    def getType(self):
        return self.getDef()['type']

    def isLocal(self):
        return self.getDef().isLocal()

    def isCombined(self):
        return self.getDef().isCombined()

    def getLocalAt(self):
        return self._properties.get('localAt')

    def getLocator(self, taskName = None):
        '''Gets the locator for this product, or None if there isn't one.
        If a task name is provided, the locator produced by that particular
        task is returned, otherwise the first reported locator is returned.
        '''
        if taskName is None:
            return self._properties.get('locator')
        else:
            return self.__producers.get(taskName)

    def getProducers(self):
        '''Returns an iterator which contains the producers of a product.
        Only the tasks that have reported a locator are included.
        The iterator contains pairs of task name and locator.
        '''
        return self.__producers.items()

    def isAvailable(self):
        return self._properties['state'] == 'done'

    def isBlocked(self):
        return self._properties['state'] == 'blocked'

    def setLocalAt(self, taskRunnerId):
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

    def storeLocator(self, locator, taskName):
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

    def done(self):
        if self._properties['state'] == 'waiting':
            self._properties['state'] = 'done'
            self._notify()

    def blocked(self):
        if self._properties['state'] == 'waiting':
            self._properties['state'] = 'blocked'
            self._notify()

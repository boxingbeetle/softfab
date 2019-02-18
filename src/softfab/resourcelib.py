# SPDX-License-Identifier: BSD-3-Clause

import logging
from typing import (
    AbstractSet, ClassVar, FrozenSet, Iterable, Iterator, Mapping, Optional,
    Set, cast
    )

from softfab.config import dbDir
from softfab.connection import ConnectionStatus
from softfab.databaselib import Database, DatabaseElem
from softfab.timelib import getTime
from softfab.utils import abstract
from softfab.xmlbind import XMLTag
from softfab.xmlgen import xml

class ResourceBase(XMLTag, DatabaseElem):
    """Base class for Resource and TaskRunner.
    """
    tagName = abstract # type: ClassVar[str]
    boolProperties = ('suspended',)
    intProperties = ('changedtime',)

    def __init__(self, properties: Mapping[str, str]):
        XMLTag.__init__(self, properties)
        DatabaseElem.__init__(self)
        self._properties.setdefault('changeduser', None)
        self._capabilities = set() # type: AbstractSet[str]

    def _addCapability(self, attributes: Mapping[str, str]) -> None:
        cast(Set[str], self._capabilities).add(attributes['name'])

    def _endParse(self) -> None:
        self._capabilities = frozenset(self._capabilities)

    def _getContent(self) -> Iterator:
        for cap in self._capabilities:
            yield xml.capability(name = cap)

    def __getitem__(self, key: str) -> object:
        if key == 'type':
            return self.typeName
        elif key == 'locator':
            return self.locator
        elif key == 'capabilities':
            return sorted(self._capabilities)
        elif key == 'changedtime':
            return self.getChangedTime()
        elif key == 'changeduser':
            return self.getChangedUser()
        else:
            return super().__getitem__(key)

    def getId(self) -> str:
        return cast(str, self._properties['id'])

    @property
    def typeName(self) -> str:
        """The name of the resource type of this resource.
        The type could be defined in `resTypeDB` or be a reserved type.
        """
        raise NotImplementedError

    @property
    def locator(self) -> str:
        """String that can be used to access this resource.
        """
        raise NotImplementedError

    @property
    def description(self) -> str:
        """String that describes this resource to the user.
        """
        return cast(str, self._properties['description'])

    @property
    def capabilities(self) -> FrozenSet[str]:
        return cast(FrozenSet[str], self._capabilities)

    @property
    def cost(self) -> int:
        """A numeric value that is used as a tie breaker when multiple resource
        assignments are possible: resources with a lower cost will be preferred
        over more costly alternatives.
        The goal is to increase the chance of being able to grant future
        resource reservations without having to wait for reserved resources
        to become available again.
        No meaning should be attached to the cost value except the ability
        to compare the sum of the costs of different resource selections.
        Different resources may have equal costs.
        """
        # Note: A more refined cost function is possible, but as a starting
        #       point we just take the number of capabilities as an indication
        #       of how valuable a resource is: more capabilities means it is
        #       more likely that it matches a resource spec that is not matched
        #       by other resources.
        return len(self._capabilities)

    def isFree(self) -> bool:
        """Returns True iff this resource is currently available."""
        return not (self.isReserved() or self.isSuspended())

    def isReserved(self) -> bool:
        """Returns True iff this resource is currently reserved."""
        raise NotImplementedError

    def isSuspended(self) -> bool:
        """Returns True iff this resource is currently suspended."""
        return cast(bool, self._properties['suspended'])

    def setSuspend(self, suspended: bool, user: str) -> None:
        """Sets the (new) suspend state on request of `user`.
        Raises TypeError if `suspended` is not a bool.
        """
        if not isinstance(suspended, bool):
            raise TypeError(type(suspended))
        if self._properties['suspended'] != suspended:
            self._properties['suspended'] = suspended
            self._properties['changedtime'] = getTime()
            self._properties['changeduser'] = user
            self._notify()

    def getChangedUser(self) -> Optional[str]:
        '''Returns the name of the user that suspended/resumed the TR as
        the last person.
        '''
        return cast(Optional[str], self._properties['changeduser'])

    def getChangedTime(self) -> int:
        '''Returns the time at which the suspend state last changed.
        '''
        return cast(int, self._properties.get('changedtime', 0))

    def getConnectionStatus(self) -> ConnectionStatus:
        '''Gets a classification of the connection between this resource and
        the Control Center. The status can be `UNKNOWN` only for a short time
        after a Control Center restart.
        If the resource does not depend on any external service, the status
        is always `CONNECTED`.
        '''
        raise NotImplementedError

    def getRun(self):
        """Returns the execution run that this resource is reserved by,
        or None if it is not currently reserved by an execution run.
        """
        raise NotImplementedError

class Resource(ResourceBase):
    """Represents an actual resource, which has an identity and state.
    """
    tagName = 'resource'

    @classmethod
    def create(
            cls, resourceId: str, resType: str, locator: str, description: str,
            capabilities: Iterable[str]
            ) -> 'Resource':
        # pylint: disable=protected-access
        resource = cls({
            'id': resourceId,
            'type': resType,
            'description': description,
            'locator': locator,
            })
        resource._capabilities = frozenset(capabilities)
        return resource

    def copyState(self, resource: 'Resource') -> None:
        myProps = self._properties
        otherProps = resource._properties # pylint: disable=protected-access
        for propName in 'reserved', 'suspended', 'changedtime', 'changeduser':
            value = otherProps.get(propName)
            if value is not None:
                myProps[propName] = value
        self._notify()

    def __getitem__(self, key: str) -> object:
        if key == 'user':
            return self._properties.get('reserved', '')
        else:
            return super().__getitem__(key)

    @property
    def typeName(self) -> str:
        return cast(str, self._properties['type'])

    @property
    def locator(self) -> str:
        return cast(str, self._properties['locator'])

    def getConnectionStatus(self) -> ConnectionStatus:
        return ConnectionStatus.CONNECTED

    def getRun(self) -> None:
        # TODO: It would be useful to be able to return the run, since then
        #       resources reserved by a run with alert status would show
        #       that alert status too.
        #       But currently resources only remember the user that reserved
        #       them, not the run. Even for Task Runners the run info is
        #       reconstructed rather than remembered.
        return None

    def isReserved(self) -> bool:
        return 'reserved' in self._properties

    def reserve(self, user: str) -> None:
        if 'reserved' in self._properties:
            logging.error(
                'Attempt to reserve resource "%s" that is already reserved',
                self.getId()
                )
        else:
            self._properties['reserved'] = user
            self._notify()

    def free(self) -> None:
        if 'reserved' in self._properties:
            del self._properties['reserved']
            self._notify()
        else:
            logging.error(
                'Attempt to free resource "%s" that is not reserved',
                self.getId()
                )

class ResourceFactory:
    @staticmethod
    def createResource(attributes: Mapping[str, str]) -> Resource:
        return Resource(attributes)

class ResourceDB(Database):
    baseDir = dbDir + '/resources'
    factory = ResourceFactory()
    privilegeObject = 'r'
    description = 'resource'
    uniqueKeys = ( 'id', )
resourceDB = ResourceDB()

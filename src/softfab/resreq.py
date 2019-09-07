# SPDX-License-Identifier: BSD-3-Clause

'''Definitions for specifying resource requirements.
'''

from typing import (
    AbstractSet, FrozenSet, Iterable, Iterator, Mapping, MutableSet, cast
)

from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLContent, xml

taskRunnerResourceRefName = 'SF_TR'

class ResourceSpec(XMLTag):
    '''Resource requirement specification.
    Defines what kind of resource is needed to execute a certain task.
    '''
    tagName = 'resource'

    @staticmethod
    def create(ref: str, resType: str, capabilities: Iterable[str]) \
            -> 'ResourceSpec':
        properties = dict(
            ref = ref,
            type = resType,
            )
        spec = ResourceSpec(properties)
        # pylint: disable=protected-access
        spec.__capabilities = frozenset(capabilities)
        return spec

    def __init__(self, properties: Mapping[str, str]):
        XMLTag.__init__(self, properties)
        self.__capabilities: AbstractSet[str] = set()

    def __repr__(self) -> str:
        return f'ResourceSpec({self.reference!r}, {self.typeName!r}, ' \
                            f'{self.__capabilities!r})'

    def _addCapability(self, attributes: Mapping[str, str]) -> None:
        cast(MutableSet, self.__capabilities).add(attributes['name'])

    def _endParse(self) -> None:
        self.__capabilities = frozenset(self.__capabilities)

    @property
    def reference(self) -> str:
        """Reference label by which to refer to this requirement.
        """
        return cast(str, self['ref'])

    @property
    def typeName(self) -> str:
        """The name of the resource type of the required resource.
        """
        return cast(str, self['type'])

    @property
    def capabilities(self) -> FrozenSet[str]:
        """An immutable set containing the required capabilities.
        """
        return cast(FrozenSet[str], self.__capabilities)

    def _getContent(self) -> XMLContent:
        for cap in self.__capabilities:
            yield xml.capability(name = cap)

class ResourceClaim:
    """Immutable collection of ResourceSpecs."""

    @classmethod
    def create(cls, specs: Iterable[ResourceSpec]) -> 'ResourceClaim':
        """Returns a ResourceClaim containing the given specs."""
        return cls({spec.reference: spec for spec in specs})

    def __init__(self, specsByRef: Mapping[str, ResourceSpec]):
        """Do not call directly; use `create` instead."""
        self.__specsByRef = specsByRef

    def __iter__(self) -> Iterator[ResourceSpec]:
        """Iterates through the specs contained in this claim,
        in no particular order.
        """
        yield from self.__specsByRef.values()

    def __bool__(self) -> bool:
        """Returns True iff this claim contains one or more specs."""
        return bool(self.__specsByRef)

    def __len__(self) -> int:
        """Returns the number of specs contained in this claim."""
        return len(self.__specsByRef)

    def iterSpecsOfType(self, typeName: str) -> Iterator[ResourceSpec]:
        """Iterates through the specs contained in this claim that request
        a resource of the type `typeName`, in no particular order.
        """
        for spec in self.__specsByRef.values():
            if spec.typeName == typeName:
                yield spec

    def merge(self, claim: 'ResourceClaim') -> 'ResourceClaim':
        """Returns a new claim containing the ResourceSpecs from this claim
        and the given claim. ResourceSpecs with the same reference will have
        their capability requirements united, unless the resource types differ,
        in which case the spec from the given claim overrides the one from
        this claim.
        """
        # pylint: disable=protected-access
        specsByRef = dict(self.__specsByRef)
        for ref, spec in claim.__specsByRef.items():
            ourSpec = specsByRef.get(ref)
            if ourSpec is None:
                specsByRef[ref] = spec
            else:
                resType = spec.typeName
                if resType == ourSpec.typeName:
                    # Merge specs.
                    specsByRef[ref] = ResourceSpec.create(
                        ref, resType,
                        spec.capabilities | ourSpec.capabilities
                        )
                else:
                    # Conflicting types; override.
                    specsByRef[ref] = spec
        return self.__class__(specsByRef)

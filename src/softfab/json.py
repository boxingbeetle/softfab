# SPDX-License-Identifier: BSD-3-Clause

"""Functions for creating data transfer objects from JSON and vice versa.
Data transfer objects are defined using the `attrs` library.
"""

from enum import Enum
from typing import Callable, Dict, Iterator, Tuple, Type, TypeVar, Union

import attr

from softfab.compat import get_args, get_origin


def dataToJSON(data: object) -> Dict[str, object]:
    """Create a dictionary representation of the given data transfer object.
    The dictionary is suitable to be converted to a JSON string.
    The data transfer object must be from a class using `attrs`.
    """

    jsonNode: Dict[str, object] = {}
    for field in attr.fields(data.__class__):
        name = field.name
        value: object = getattr(data, name)
        if isinstance(value, (str, int, float)):
            jsonNode[name] = value
        elif isinstance(value, Enum):
            jsonNode[name] = value.name.lower()
        else:
            raise TypeError(value.__class__.__name__)
    return jsonNode

def _describeType(typ: type) -> str:
    """Describe the given Python type in a way that makes sense for
    a user providing data in JSON format.
    """
    if issubclass(typ, str):
        return 'string'
    elif issubclass(typ, bool):
        return 'Boolean'
    elif issubclass(typ, int):
        return 'integer'
    elif issubclass(typ, float):
        return 'floating point'
    elif hasattr(typ, 'items'):
        return 'object'
    elif hasattr(typ, '__iter__'):
        return 'array'
    else:
        return typ.__name__

def mapJSON(jsonNode: object,
            cls: Type,
            partial: bool = True
            ) -> Dict[str, object]:
    """Map a JSON object to a data transfer class.

    @param partial: If L{False}, raise L{ValueError} when not all class
        fields occur in the JSON object.
    @return: A dictionary mapping field name to value.
    @raise ValueError: If the structure of the JSON data does not map
        to the given data transfer class.
    """

    iterItems: Callable[[], Iterator[Tuple[str, object]]]
    try:
        iterItems = getattr(jsonNode, 'items')
    except AttributeError:
        raise ValueError(f"Expected object, "
                         f"got {_describeType(jsonNode.__class__)}'")

    fields = attr.fields_dict(cls)
    kwargs: Dict[str, object] = {}
    for name, value in iterItems():
        try:
            attrib = fields.pop(name)
        except KeyError:
            raise ValueError(f"Field '{name}' does not exist")

        attribType = attrib.type
        if attribType is None:
            # We raise TypeError since this is an error on the data
            # transfer class instead of invalid JSON data.
            raise TypeError(f"No type specified for attribute '{name}'")

        optional = False
        if get_origin(attribType) is Union:
            valueType = None
            for typ in get_args(attribType):
                if typ is type(None):
                    optional = True
                elif valueType is None:
                    valueType = typ
                else:
                    raise TypeError(f"Ambiguous type for attribute '{name}'")
            # The typing module will remove duplicate types and reduce
            # one-type unions to just that type.
            assert valueType is not None
            attribType = valueType

        if value is None and optional:
            kwargs[name] = None
        elif issubclass(attribType, Enum):
            if not isinstance(value, str):
                raise ValueError(f"Expected string value for field '{name}'")
            memberName = value.upper()
            try:
                kwargs[name] = attribType.__members__[memberName]
            except KeyError:
                raise ValueError(
                    f"Invalid value '{value}' for field '{name}'; "
                    f"expected one of: " + ', '.join(
                        mbr.lower() for mbr in attribType.__members__))
        else:
            if not isinstance(value, attribType):
                raise ValueError(f"Expected {_describeType(attribType)} "
                                 f"value for field '{name}'")
            kwargs[name] = value

    if not partial:
        missing = [name for name, attrib in fields.items()
                   if attrib.default is attr.NOTHING]
        if missing:
            raise ValueError(f"Missing values for fields: {', '.join(missing)}")

    return kwargs

T = TypeVar('T')

def jsonToData(jsonNode: object, cls: Type[T]) -> T:
    """Create a data transfer object from a JSON dictionary.
    Raise ValueError if the structure of the JSON data does not map
    to the given data transfer class.
    """

    kwargs = mapJSON(jsonNode, cls, partial=False)
    return cls(**kwargs) # type: ignore[call-arg]

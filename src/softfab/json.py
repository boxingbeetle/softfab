# SPDX-License-Identifier: BSD-3-Clause

"""Functions for creating data transfer objects from JSON and vice versa.
Data transfer objects are defined using the `attrs` library.
"""

from enum import Enum
from typing import Dict

import attr


def dataToJSON(data: object) -> Dict[str, object]:
    """Create a dictionary representation of the given data transfer object.
    The dictionary is suitable to be converted to a JSON string.
    The data transfer object must be from a class using `attrs`.
    """

    jsonNode: Dict[str, object] = {}
    for field in attr.fields(data.__class__):
        name = field.name
        value = getattr(data, name)
        if isinstance(value, (str, int, float)):
            jsonNode[name] = value
        elif isinstance(value, Enum):
            jsonNode[name] = value.name.lower()
        else:
            raise TypeError(value.__class__.__name__)
    return jsonNode

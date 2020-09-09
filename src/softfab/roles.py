# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from functools import total_ordering
from typing import AbstractSet, cast

roleNames = frozenset([ 'guest', 'user', 'operator' ])

# This only defines UI ordering.
# The content of the list must be consistent with roleNames.
@total_ordering
class UIRoleNames(Enum):
    INACTIVE = 1
    GUEST = 2
    USER = 3
    OPERATOR = 4
    def __lt__(self, other: object) -> bool:
        if self.__class__ is other.__class__:
            # pylint: disable=comparison-with-callable
            # https://github.com/PyCQA/pylint/issues/2757
            return self.value < cast(Enum, other).value
        return NotImplemented
assert {elem.name.lower() for elem in list(UIRoleNames)[1:]} == roleNames

def uiRoleToSet(role: UIRoleNames) -> AbstractSet[str]:
    '''The opposite transformation of `UserAccount.uiRole`.
    '''
    return set() if role is UIRoleNames.INACTIVE else { role.name.lower() }

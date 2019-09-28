# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import Iterable, Optional


class ResultCode(Enum):
    """Result codes for tasks and jobs.
    """

    OK = 1
    """Process was correct, content was correct."""

    CANCELLED = 2
    """Will never get a result."""

    WARNING = 3
    """Process was correct, content had problems."""

    ERROR = 4
    """Process had problems, content unknown."""

    INSPECT = 5
    """Waiting for postponed inspection."""

def combineResults(items: Iterable) -> Optional[ResultCode]:
    '''Computes the result over a series of items.
    Returns the ResultCode of the worst item result, or None if none of the
    items has a result.
    Each item must have a `result` property that returns a ResultCode or None.
    '''
    return max(
        (item.result for item in items),
        default=None,
        key=lambda result: 0 if result is None else result.value
        )

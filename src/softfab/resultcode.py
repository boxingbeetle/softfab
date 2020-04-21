# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from functools import total_ordering


@total_ordering
class ResultCode(Enum):
    """Result codes for tasks and jobs.
    Result codes can be compared to each other and to None;
    the more urgent result is considered greater and
    all results are greater than None.
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

    def __hash__(self) -> int:
        return self.value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ResultCode):
            # pylint: disable=comparison-with-callable
            # https://github.com/PyCQA/pylint/issues/2306
            return self.value == other.value
        elif other is None:
            return False
        else:
            return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, ResultCode):
            # pylint: disable=comparison-with-callable
            return self.value > other.value
        elif other is None:
            return True
        else:
            return NotImplemented

# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum

ResultCode = Enum('ResultCode', 'OK CANCELLED WARNING ERROR INSPECT')
'''Result codes for tasks and jobs.
The meaning of the different values:
ok: process was correct, content was correct;
warning: process was correct, content had problems;
error: process had problems;
inspect: waiting for postponed inspection;
cancelled: will never get a result.
'''

def combineResults(items):
    '''Computes the result over a series of items.
    Returns the ResultCode of the worst item result, or None if none of the
    items has a result.
    Each item must have a getResult() method that returns a ResultCode.
    '''
    return max(
        (item.getResult() for item in items),
        default=None,
        key=lambda result: 0 if result is None else result.value
        )

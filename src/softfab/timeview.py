# SPDX-License-Identifier: BSD-3-Clause

from typing import Optional
import time

_dateFormat = '%Y-%m-%d'
_timeFormat = _dateFormat + ' %H:%M'

def formatDuration(sec: Optional[int]) -> str:
    '''Formats the given duration in seconds as a string: DD - HH:MM:SS,
    with leading zero parts are dropped.
    '''
    if sec is None:
        return '-'
    else:
        ret = ''
        for value, sep in [
            ( sec // 86400, 'd '),
            ( (sec // 3600) % 24, ':'),
            ( (sec // 60) % 60, ':'),
            ( sec % 60, ''),
            ]:
            if value != 0 or ret != '' or sep == '':
                if value < 10 and ret != '':
                    ret += '0'
                ret += str(value) + sep
        return ret

def formatDate(sec: Optional[int]) -> str:
    if sec is None:
        return '-'
    else:
        return time.strftime(_dateFormat, time.localtime(sec))

def formatTime(sec: Optional[int]) -> str:
    if sec is None:
        return '-'
    else:
        return time.strftime(_timeFormat, time.localtime(sec))

def formatTimeAttr(sec: Optional[int]) -> Optional[str]:
    '''Formats a timestamp for use as an XML attribute value.
    '''
    if sec is None:
        return None
    else:
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(sec))

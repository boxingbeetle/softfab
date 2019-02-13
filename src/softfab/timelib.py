# SPDX-License-Identifier: BSD-3-Clause

from time import localtime, mktime, struct_time, time
from typing import Callable, Iterator, Sequence, Tuple, cast
import re

_numOfDays = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

_timePattern = re.compile(
    r'\s*((?:20)?\d\d)([-./])(0?[1-9]|1[0-2])\2(0?[1-9]|[12]\d|3[01])'
    r'(?:\s+([01]?\d|2[0-3])[:.]([0-5]\d))?\s*$'
    )

secondsPerDay = 24 * 60 * 60
# Approximation of the time the sun becomes a red giant.
#   http://en.wikipedia.org/wiki/Sun#Life_cycle
# The exact number is not really important, what matters is that it is larger
# than any ordinary timestamp.
endOfTime = 5000000000 * 365 * secondsPerDay

class TimeSource:
    '''Design for testability: the time source can be overridden by unit tests.
    '''

    def __init__(self) -> None:
        self.__timeSource = lambda: int(time())

    def getTime(self) -> int:
        '''Gets the current time in seconds since the epoch.
        All code should use this function instead of accessing the Python "time"
        module directly, so unit tests can override the time source and have
        full control over the flow of time.
        '''
        return self.__timeSource()

    def setTimeFunc(self, func: Callable[[], int]) -> None:
        '''Overrides the global time source: the given function will be called
        to provide the current time. The unit tests can use this to run tests
        with a fully programmable clock rather than using the wall clock.
        '''
        assert callable(func)
        self.__timeSource = func

    def setTime(self, timestamp: int) -> None:
        '''Convenience function which sets the time to the given time stamp.
        The time will be frozen: that same time stamp is returned every time.
        '''
        assert isinstance(timestamp, int)
        self.__timeSource = lambda: timestamp

timeSource = TimeSource()
# For easy importing:
getTime = timeSource.getTime
setTimeFunc = timeSource.setTimeFunc
setTime = timeSource.setTime

def _intsToTime(pieces: Sequence[int]) -> int:
    return int(mktime(
        cast(Tuple[int, int, int, int, int, int, int, int, int], tuple(pieces))
        ))

def stringToTime(text: str, up: bool = False) -> int:
    '''Parses a date string.
    Returns the number of seconds since 1970.
    If the "up" argument is False, returns the first second of the day,
    if it is True, returns the last second of the day.
    Raises ValueError if the string is not a valid date.
    '''
    match = _timePattern.match(text)
    if match is None:
        raise ValueError('Invalid date: "%s"' % text)
    if match.lastindex >= 6:
        pieces = [ int(num) for num in match.group(1, 3, 4, 5, 6) ]
        if up:
            pieces.append(59)
        else:
            pieces.append(0)
    else:
        pieces = [ int(num) for num in match.group(1, 3, 4) ]
        if up:
            pieces += [ 23, 59, 59 ]
        else:
            pieces += [ 0, 0, 0 ]
    pieces += [ 0, 0, -1 ]
    if pieces[2] > _numOfDays[pieces[1]]:
        if pieces[1] != 2 or pieces[2] > 29:
            raise ValueError(
                'Invalid date: "%s" (month does not have %d days)'
                % ( text, pieces[2] )
                )
        year = pieces[0]
        if (year % 4) != 0 or ((year % 100) == 0 and (year % 400) != 0):
            raise ValueError(
                'Invalid date: "%s" (%d is not a leap year)'
                % ( text, year )
                )
    return _intsToTime(pieces)

def getWeekNr(localTime: struct_time) -> int:
    '''Returns the week number for the given timestamp.

    Weeks start at Monday. A week is considered part of the year that
    the majority of its days fall into.
    Our definition is equivalent to ISO 8601's week numbering:
      https://en.wikipedia.org/wiki/ISO_week_date

    Returns 0 if the given timetamp belongs to the last week of
    the previous year.
    '''

    lastMonday = localTime[7] - localTime[6]
    return (lastMonday + 9) // 7

def weeksInYear(year: int) -> int:
    '''Returns the maximum week number in the given year.
    See getWeekNr for a discussion of week numbering.
    '''
    # What weekday is January 1st?
    timeStruct = localtime(mktime((year, 1, 1, 0, 0, 0, 0, 0, -1)))
    weekday = timeStruct[6]
    # How many days does this year have?
    if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        days = 366
    else:
        days = 365
    # How many days fall into week 53?
    daysInWeek1 = 7 - weekday
    if daysInWeek1 < 4:
        # In this case, the week of January 1st belongs to the previous year.
        daysInWeek1 = 7
    daysInWeek53 = days - daysInWeek1 - 7 * 51
    # Week 53 belongs to this year if 4 days fall into this year.
    if daysInWeek53 < 4:
        return 52
    else:
        return 53

def normalizeWeek(year: int, week: int) -> Tuple[int, int]:
    '''Takes a year and week number within that year, where the week number may
    be out of range. Returns a year and a week number tuple, where the week
    number is an existing week of that year. For in-range weeks, the output is
    the same as the input; for out-of-range weeks, the year and week output
    correspond to the same week that is indicated by the input. For example,
    week 0 of year N is converted to the last week (52 or 53) of year N - 1.
    '''
    # Sanity check to avoid outrageously large week numbers.
    # (Python does not have a limit on the size of numbers.)
    if not -10000 < week < 10000:
        raise ValueError(week)

    while week < 1:
        year -= 1
        week += weeksInYear(year)
    while week > weeksInYear(year):
        week -= weeksInYear(year)
        year += 1
    return year, week

def toMidnight(secs: int) -> int:
    '''Returns the midnight that is closest to the given time.
    Does not round correctly for days on which the daylight saving time
    switches, but functions correctly if you avoid the hour on the middle
    of those days.
    '''
    day = cast(Tuple[int, ...], localtime(secs + secondsPerDay // 2))
    return _intsToTime(day[:3] + (0,) * 5 + (-1,))

def weekRange(year: int, week: int) -> Tuple[int, int]:
    '''Returns a pair (start, end) of time values,
    which are the times at which the given week starts and ends.
    '''
    fourthOfJanuary = _intsToTime((year, 1, 4, 0, 0, 0, 0, 0, -1))
    fourthOfJanuaryDayOfWeek = localtime(fourthOfJanuary)[6]
    mondayOfWeekOne = fourthOfJanuary - fourthOfJanuaryDayOfWeek * secondsPerDay
    beginWeek = toMidnight(mondayOfWeekOne + (week - 1) * 7 * secondsPerDay)
    endWeek = toMidnight(beginWeek + 7 * secondsPerDay)
    return beginWeek, endWeek

def iterDays(secs: int) -> Iterator[int]:
    '''Iterates through the start of consequetive days, starting with the
    start of the day that contains given time stamp.
    Each returned item is a number of seconds since 1970.
    This iterator does not stop, although the Python time module has limits.
    '''
    given = cast(Sequence[int], localtime(secs))
    dayStart = list(given)[:3] + [0, 0, 0, 0, 0, -1]
    while True:
        yield _intsToTime(dayStart)
        dayStart[2] += 1

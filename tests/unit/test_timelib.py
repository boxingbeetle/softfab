# SPDX-License-Identifier: BSD-3-Clause

from softfab import timelib
import time, unittest

def getDaysInMonth(year, month):
    if month == 2 and year % 4 == 0:
        return 29
    else:
        return (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month]

class TestTime(unittest.TestCase):
    "Test time manipulation library."

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)

    def checkDate(self, year, month, day):
        bareStruct = (year, month, day, 0, 0, 0, 0, 0, -1)
        timeSecs = int(time.mktime(bareStruct))
        timeStruct = time.localtime(timeSecs)

        # Sanity check on results returned by Python lib.
        self.assertEqual(bareStruct[ : 3], timeStruct[ : 3])

        # Calculate week number.
        weekNr = timelib.getWeekNr(timeStruct)

        # Sanity checks on week number.
        self.assertTrue(0 <= weekNr <= 53)
        if month == 1 and day == 4:
            # Week 1 contains January 4th, by definition.
            self.assertEqual(weekNr, 1)

        # Calculate start and end of week.
        weekStart, weekEnd = timelib.weekRange(year, weekNr)
        weekStartStruct = time.localtime(weekStart)
        weekEndStruct = time.localtime(weekEnd)

        # Check that the given day is indeed in the computed week.
        self.assertTrue(weekStart <= timeSecs < weekEnd)

        # Check that week start and end are on midnight on Monday.
        self.assertEqual(time.localtime(weekStart)[3 : 7], ( 0, 0, 0, 0 ))
        self.assertEqual(time.localtime(weekEnd)[3 : 7], ( 0, 0, 0, 0 ))

        # Check the week number of the week start.
        if weekStartStruct[0] == year:
            self.assertEqual(timelib.getWeekNr(weekStartStruct), weekNr)
        else:
            self.assertEqual(weekStartStruct[0], year - 1)
            self.assertTrue(0 <= weekNr <= 1)

        # Check the week number of the week end.
        if weekEndStruct[0] == year:
            self.assertEqual(timelib.getWeekNr(weekEndStruct), weekNr + 1)
        else:
            self.assertEqual(weekEndStruct[0], year + 1)
            self.assertTrue(52 <= weekNr <= 53)

    def test0010WeeksInYear(self):
        """Test "weeksInYear" function by querying a couple of years for which
        the result was manually determined.
        """
        self.assertEqual(timelib.weeksInYear(2000), 52)
        self.assertEqual(timelib.weeksInYear(2001), 52)
        self.assertEqual(timelib.weeksInYear(2002), 52)
        self.assertEqual(timelib.weeksInYear(2003), 52)
        self.assertEqual(timelib.weeksInYear(2004), 53)
        self.assertEqual(timelib.weeksInYear(2005), 52)
        self.assertEqual(timelib.weeksInYear(2006), 52)
        self.assertEqual(timelib.weeksInYear(2007), 52)
        self.assertEqual(timelib.weeksInYear(2008), 52)
        self.assertEqual(timelib.weeksInYear(2009), 53)
        self.assertEqual(timelib.weeksInYear(2010), 52)

    def test0011WeeksInYear(self):
        """Test "weeksInYear" function by determining whether week 1 of the next
        year is indeed that many weeks ahead.
        """
        for year in range(1970, 2038):
            # The 4th of January is guaranteed to be in week 1.
            # Jump ahead exactly N weeks, where N is the number of weeks in this
            # year, according to the function under test.
            secs = (
                time.mktime((year, 1, 4, 0, 0, 0, 0, 0, -1))
                + timelib.weeksInYear(year) * 7 * timelib.secondsPerDay
                + timelib.secondsPerDay // 2 # compensate for leap seconds etc
                )
            # Go to start of the week (last Monday).
            dayOfWeek = time.localtime(secs)[6]
            secs -= dayOfWeek * timelib.secondsPerDay
            # Count the number of days in this week that belong to the next year
            # and check if we see January 4th.
            daysInYear = 0
            jan4 = False
            for day in range(7):
                ymd = time.localtime(secs)[ : 3]
                if ymd[ : 2] == ( year + 1, 1 ):
                    daysInYear += 1
                if ymd == ( year + 1, 1, 4 ):
                    jan4 = True
                secs += timelib.secondsPerDay
            # The majority of days must be in the new year.
            self.assertTrue(daysInYear >= 4)
            # The week must contain January 4th.
            self.assertTrue(jan4)

    def test0020NormalizeWeek(self):
        '''Test "normalizeWeek" function.
        '''
        self.assertEqual(timelib.normalizeWeek(1996, 23), (1996, 23))
        self.assertEqual(timelib.normalizeWeek(1999, 53), (2000,  1))
        self.assertEqual(timelib.normalizeWeek(2001,  0), (2000, 52))
        self.assertEqual(timelib.normalizeWeek(2005,  0), (2004, 53))

    def test0030IterDays(self):
        '''Test "iterDays" function.
        '''
        gen = timelib.iterDays(time.mktime(time.localtime()))
        prevTimestamp = None
        for _ in range(4000):
            timestamp = next(gen)
            dayStart = time.localtime(timestamp)
            # One day always lasts between 23 and 25 hours.
            if prevTimestamp is not None:
                seconds = timestamp - prevTimestamp
                self.assertTrue(23 * 60 * 60 <= seconds <= 25 * 60 * 60, seconds)
            # Check that the time stamp is at midnight.
            self.assertEqual(dayStart[3 : 6], (0, 0, 0), dayStart)
            prevTimestamp = timestamp

    def test0100Mixed(self):
        """Test a large range of dates for various properties.
        """
        # Note: Python 2.3.3 under Linux doesn't accept dates
        #       before 1970 or after 2038-01-17.
        for year in range(1970, 2038):
            for month in range(1, 13):
                for day in range(1, getDaysInMonth(year, month) + 1):
                    try:
                        # Perform actual tests.
                        self.checkDate(year, month, day)
                    except:
                        print(('Date for which check failed: %04d-%02d-%02d' % (
                            year, month, day
                            )))
                        raise

if __name__ == '__main__':
    unittest.main()

# SPDX-License-Identifier: BSD-3-Clause

from softfab.utils import cachedProperty

import unittest


# Classes under test:

class Base(object):
    '''Most basic use case.
    '''

    def __init__(self, valueFunc):
        self._valueFunc = valueFunc

    @cachedProperty
    def description(self):
        return self._valueFunc()

class Dual(object):
    '''Basic use case with two cached properties.
    '''

    def __init__(self, valueFunc):
        self._valueFunc = valueFunc

    @cachedProperty
    def description(self):
        return self._valueFunc()

    @cachedProperty
    def description2(self):
        return self._valueFunc()

class Inherit(Base):
    '''Inheritance without any overrides.
    '''

    pass

class Override(Base):
    '''Override the cached property with another cached property.
    '''

    @cachedProperty
    def description(self):
        return self._valueFunc()

class OverrideNonCached(Base):
    '''Override the cached property with a non-cached property.
    '''

    @property
    def description(self):
        return self._valueFunc()


class SuperSingle(Base):
    '''Subclass value is computed from superclass value.
    '''

    @cachedProperty
    def description(self):
        return super(SuperSingle, self).description + ' sub'

class SuperDual(Base):
    '''Subclass value is computed from superclass value.
    '''

    @cachedProperty
    def description(self):
        return super(SuperDual, self).description + ' sub'

    @cachedProperty
    def description2(self):
        return super(SuperDual, self).description + ' sub2'


# Classes that perform the tests:

class CallCounter(object):
    '''Helper class that counts how often the value is retrieved.
    This can be used to verify that the value is actually cached.
    '''

    def __init__(self, testValue):
        self.called = 0
        self.testValue = testValue

    def __call__(self):
        self.called += 1
        return self.testValue

def createTestValue(repeat):
    return 'very nice %d' % repeat

class TestCachedProperty(unittest.TestCase):
    '''Test the CachedProperty class.
    '''

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)

    def check(self, objFactory, valueFactory=createTestValue, suffix=None):
        # Create multiple objects, because some things should be computed per
        # class and some per object.
        for repeat in range(3):
            value = valueFactory(repeat)
            counter = CallCounter(value)
            expectedValue = value if suffix is None else value + ' ' + suffix

            obj = objFactory(counter)
            # First time the get method should be called.
            self.assertEqual(obj.description, expectedValue)
            self.assertEqual(counter.called, 1)
            # Second time the cached value should be returned.
            self.assertEqual(obj.description, expectedValue)
            self.assertEqual(counter.called, 1)

    def checkError(self, objFactory, badFunc):
        # Create multiple objects, because some things should be computed per
        # class and some per object.
        for repeat in range(3):
            counter = CallCounter('very nice %d' % repeat)
            obj = objFactory(counter)
            # Try the bad behaviour before the get method is called.
            self.assertRaises(AttributeError, lambda: badFunc(obj))
            # First time the get method should be called.
            self.assertEqual(obj.description, counter.testValue)
            self.assertEqual(counter.called, 1)
            # Try the bad behaviour after the get method is called.
            self.assertRaises(AttributeError, lambda: badFunc(obj))
            # Second time the cached value should be returned.
            self.assertEqual(obj.description, counter.testValue)
            self.assertEqual(counter.called, 1)
            # Try the bad behaviour after the caching has been confirmed.
            self.assertRaises(AttributeError, lambda: badFunc(obj))

    def test0100Base(self):
        '''Test the most straightforward use case.
        '''
        self.check(Base)

    def test0110Dual(self):
        '''Test two properties in one class.
        '''
        self.check(Dual)

        counter = CallCounter(createTestValue(123))
        obj = Dual(counter)
        self.assertEqual(obj.description, counter.testValue)
        self.assertEqual(counter.called, 1)
        self.assertEqual(obj.description2, counter.testValue)
        self.assertEqual(counter.called, 2)
        self.assertEqual(obj.description, counter.testValue)
        self.assertEqual(counter.called, 2)
        self.assertEqual(obj.description2, counter.testValue)
        self.assertEqual(counter.called, 2)

    def test0200Inherit(self):
        '''Test inheritance of a class that contains a cached property.
        '''
        self.check(Inherit)

    def test0300Override(self):
        '''Test overriding cached property with another cached property.
        '''
        self.check(Override)

    def test0310OverrideNonCached(self):
        '''Test overriding cached property with non-cached property.
        '''
        counter = CallCounter(createTestValue(123))
        obj = OverrideNonCached(counter)
        # The get method should be called every time.
        self.assertEqual(obj.description, counter.testValue)
        self.assertEqual(counter.called, 1)
        self.assertEqual(obj.description, counter.testValue)
        self.assertEqual(counter.called, 2)
        self.assertEqual(obj.description, counter.testValue)
        self.assertEqual(counter.called, 3)

    def test0400Super(self):
        '''Test computing subclass value based on superclass value.
        '''
        self.check(SuperSingle, suffix='sub')

    def test0410Dual(self):
        '''Test computing subclass value based on superclass value.
        '''
        self.check(SuperDual, suffix='sub')

        # Verify that second property actually gets the superclass value
        # of the first property rather than the cached subclass value.
        counter = CallCounter(createTestValue(123))
        obj = SuperDual(counter)
        self.assertEqual(obj.description, counter.testValue + ' sub')
        self.assertEqual(obj.description2, counter.testValue + ' sub2')

    def test0500Set(self):
        '''Try to write to a cached property.
        '''
        def setValue(obj):
            obj.description = 'new description'
        self.checkError(Base, setValue)

    def test0510Del(self):
        '''Try to delete a cached property.
        '''
        def delete(obj):
            del obj.description
        self.checkError(Base, delete)

    def test0600NoneValue(self):
        '''Test whether a return value of "None" is cached.
        '''
        self.check(Base, lambda repeat: None)
        self.check(Inherit, lambda repeat: None)

    def test0610ClassAttributeAccess(self):
        '''Test what happens if the property is looked up on a class
        instead of an object.
        '''
        self.assertEqual(
            Base.description,
            Base.__dict__['description']
            )

if __name__ == '__main__':
    unittest.main()

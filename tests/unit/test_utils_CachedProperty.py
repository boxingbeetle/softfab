# SPDX-License-Identifier: BSD-3-Clause

"""Test the CachedProperty class."""

from pytest import raises

from softfab.utils import cachedProperty


# Classes under test:

class Base:
    """Most basic use case."""

    def __init__(self, valueFunc):
        self._valueFunc = valueFunc

    @cachedProperty
    def description(self):
        return self._valueFunc()

class Dual:
    """Basic use case with two cached properties."""

    def __init__(self, valueFunc):
        self._valueFunc = valueFunc

    @cachedProperty
    def description(self):
        return self._valueFunc()

    @cachedProperty
    def description2(self):
        return self._valueFunc()

class Inherit(Base):
    """Inheritance without any overrides."""

class Override(Base):
    """Override the cached property with another cached property."""

    @cachedProperty
    def description(self):
        return self._valueFunc()

class OverrideNonCached(Base):
    """Override the cached property with a non-cached property."""

    @property
    def description(self):
        return self._valueFunc()


class SuperSingle(Base):
    """Subclass value is computed from superclass value."""

    @cachedProperty
    def description(self):
        return super(SuperSingle, self).description + ' sub'

class SuperDual(Base):
    """Subclass value is computed from superclass value."""

    @cachedProperty
    def description(self):
        return super(SuperDual, self).description + ' sub'

    @cachedProperty
    def description2(self):
        return super(SuperDual, self).description + ' sub2'


# Code that performs the tests:

class CallCounter:
    """Helper class that counts how often the value is retrieved.
    This can be used to verify that the value is actually cached.
    """

    def __init__(self, testValue):
        self.called = 0
        self.testValue = testValue

    def __call__(self):
        self.called += 1
        return self.testValue

def createTestValue(repeat):
    return 'very nice %d' % repeat

def check(objFactory, valueFactory=createTestValue, suffix=None):
    # Create multiple objects, because some things should be computed per
    # class and some per object.
    for repeat in range(3):
        value = valueFactory(repeat)
        counter = CallCounter(value)
        expectedValue = value if suffix is None else value + ' ' + suffix

        obj = objFactory(counter)
        # First time the get method should be called.
        assert obj.description == expectedValue
        assert counter.called == 1
        # Second time the cached value should be returned.
        assert obj.description == expectedValue
        assert counter.called == 1

def checkError(objFactory, badFunc):
    # Create multiple objects, because some things should be computed per
    # class and some per object.
    for repeat in range(3):
        counter = CallCounter('very nice %d' % repeat)
        obj = objFactory(counter)
        # Try the bad behaviour before the get method is called.
        with raises(AttributeError):
            badFunc(obj)
        # First time the get method should be called.
        assert obj.description == counter.testValue
        assert counter.called == 1
        # Try the bad behaviour after the get method is called.
        with raises(AttributeError):
            badFunc(obj)
        # Second time the cached value should be returned.
        assert obj.description == counter.testValue
        assert counter.called == 1
        # Try the bad behaviour after the caching has been confirmed.
        with raises(AttributeError):
            badFunc(obj)

def testCachedPropertyBase():
    """Test the most straightforward use case."""
    check(Base)

def testCachedPropertyDual():
    """Test two properties in one class."""
    check(Dual)

    counter = CallCounter(createTestValue(123))
    obj = Dual(counter)
    assert obj.description == counter.testValue
    assert counter.called == 1
    assert obj.description2 == counter.testValue
    assert counter.called == 2
    assert obj.description == counter.testValue
    assert counter.called == 2
    assert obj.description2 == counter.testValue
    assert counter.called == 2

def testCachedPropertyInherit():
    """Test inheritance of a class that contains a cached property."""
    check(Inherit)

def testCachedPropertyOverride():
    """Test overriding cached property with another cached property."""
    check(Override)

def testCachedPropertyOverrideNonCached():
    """Test overriding cached property with non-cached property."""
    counter = CallCounter(createTestValue(123))
    obj = OverrideNonCached(counter)
    # The get method should be called every time.
    assert obj.description == counter.testValue
    assert counter.called == 1
    assert obj.description == counter.testValue
    assert counter.called == 2
    assert obj.description == counter.testValue
    assert counter.called == 3

def testCachedPropertySuper():
    """Test computing subclass value based on superclass value."""
    check(SuperSingle, suffix='sub')

def testCachedPropertySuperDual():
    """Test computing subclass value based on superclass value."""
    check(SuperDual, suffix='sub')

    # Verify that second property actually gets the superclass value
    # of the first property rather than the cached subclass value.
    counter = CallCounter(createTestValue(123))
    obj = SuperDual(counter)
    assert obj.description == counter.testValue + ' sub'
    assert obj.description2 == counter.testValue + ' sub2'

def testCachedPropertySet():
    """Try to write to a cached property."""
    def setValue(obj):
        obj.description = 'new description'
    checkError(Base, setValue)

def testCachedPropertyDel():
    """Try to delete a cached property."""
    def delete(obj):
        del obj.description
    checkError(Base, delete)

def testCachedPropertyNoneValue():
    """Test whether a return value of "None" is cached."""
    check(Base, lambda repeat: None)
    check(Inherit, lambda repeat: None)

def testCachedPropertyClassAttributeAccess():
    """Test what happens if the property is looked up on a class
    instead of an object.
    """
    assert Base.description == Base.__dict__['description']

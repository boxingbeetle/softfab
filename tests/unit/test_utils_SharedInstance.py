# SPDX-License-Identifier: BSD-3-Clause

"""Test the SharedInstance class."""

from abc import ABC, abstractmethod

from pytest import raises

from softfab.utils import SharedInstance


# Classes under test:

BASE_VALUE = 123

class Base(ABC):

    instance = SharedInstance()

    def __init__(self):
        self.value = BASE_VALUE

    def get_value(self):
        return self.value

SUB_VALUE = 456

class Sub(Base):

    def __init__(self):
        self.value = SUB_VALUE

class Abstract(Base):

    @abstractmethod
    def set_value(self, value):
        raise NotImplementedError

class Concrete(Abstract):

    def set_value(self, value):
        self.value = value


# Test cases:

def testSharedInstanceBase():
    """Test the most straightforward use case."""
    instance = Base.instance
    assert isinstance(instance, Base)
    assert instance.value == BASE_VALUE
    assert instance.get_value() == BASE_VALUE
    assert instance is Base.instance

def testSharedInstanceSub():
    """Test whether a subclass instance refers to the subclass."""
    instance = Sub.instance
    assert isinstance(instance, Base)
    assert isinstance(instance, Sub)
    assert instance.value == SUB_VALUE
    assert instance.get_value() == SUB_VALUE
    assert instance is not Base.instance
    assert instance is Sub.instance

def testSharedInstanceABC():
    """Test interaction with Abstract Base Classes."""
    with raises(TypeError):
        Abstract.instance

    instance = Concrete.instance
    assert isinstance(instance, Base)
    assert isinstance(instance, Abstract)
    assert isinstance(instance, Concrete)
    assert instance.value == BASE_VALUE
    assert instance.get_value() == BASE_VALUE
    assert instance is not Base.instance
    assert instance is Concrete.instance

    instance.set_value(789)
    assert instance.value == 789
    assert instance.get_value() == 789

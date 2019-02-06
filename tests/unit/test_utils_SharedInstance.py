# SPDX-License-Identifier: BSD-3-Clause

from utils import SharedInstance

import unittest
from abc import ABC, abstractmethod

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

# Classes that perform the tests:

class TestCachedProperty(unittest.TestCase):
    '''Test the SharedInstance class.
    '''

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)

    def test0100Base(self):
        '''Test the most straightforward use case.
        '''
        instance = Base.instance
        self.assertIsInstance(instance, Base)
        self.assertEqual(instance.value, BASE_VALUE)
        self.assertEqual(instance.get_value(), BASE_VALUE)
        self.assertIs(instance, Base.instance)

    def test0200Sub(self):
        '''Test whether a subclass instance refers to the subclass.
        '''
        instance = Sub.instance
        self.assertIsInstance(instance, Base)
        self.assertIsInstance(instance, Sub)
        self.assertEqual(instance.value, SUB_VALUE)
        self.assertEqual(instance.get_value(), SUB_VALUE)
        self.assertIsNot(instance, Base.instance)
        self.assertIs(instance, Sub.instance)

    def test0300ABC(self):
        '''Test interaction with Abstract Base Classes.
        '''
        self.assertRaises(TypeError, lambda: Abstract.instance)

        instance = Concrete.instance
        self.assertIsInstance(instance, Base)
        self.assertIsInstance(instance, Abstract)
        self.assertIsInstance(instance, Concrete)
        self.assertEqual(instance.value, BASE_VALUE)
        self.assertEqual(instance.get_value(), BASE_VALUE)
        self.assertIsNot(instance, Base.instance)
        self.assertIs(instance, Concrete.instance)

        instance.set_value(789)
        self.assertEqual(instance.value, 789)
        self.assertEqual(instance.get_value(), 789)

if __name__ == '__main__':
    unittest.main()

# SPDX-License-Identifier: BSD-3-Clause

from abc import ABCMeta
from codecs import getencoder
from contextlib import contextmanager
from itertools import islice
from typing import (
    IO, Any, Callable, Generic, Iterable, Iterator, List, Mapping, Match,
    Optional, Pattern, Sized, Tuple, Type, TypeVar, Union, cast
)
from urllib.parse import quote_plus
import os
import os.path
import re

C = TypeVar('C')
T = TypeVar('T')
KT = TypeVar('KT')
VT = TypeVar('VT')

utf8encode = getencoder('utf-8')

class IllegalStateError(Exception):
    '''Raised when an object receives a request that is not valid for the
    current state of the object.
    '''

class Heap(Generic[T]):
    """Implements the heap data structure:
    an ordered set for which it is efficient to retrieve and remove
    the smallest item.
    Typically used for priority queues.
    Note: The storage space allocated internally never shrinks,
        because for the current use it is unnecessary.
    """

    def __init__(
            self,
            size: int = 0,
            key: Optional[Callable[[T], object]] = None
            ):
        if size < 1:
            size = 1
        self.__array = [ None ] * size # type: List[Optional[T]]
        self.__count = 1
        self.__keyFunc = (lambda x: x) if key is None else key

    def __iter__(self) -> 'Heap[T]':
        """Note: This heap's iterator is destructive:
        each iteration removes the smallest element from the heap.
        """
        return self

    #def __contains__(self, item):
    #    return item in self.__array[:self.__count]

    def __moveUp(self, item: T, this: int) -> None:
        key = self.__keyFunc
        while this > 0:
            nextIndex = (this - 1) // 2
            if key(item) >= key(self.__array[nextIndex]):
                break
            self.__array[this] = self.__array[nextIndex]
            this = nextIndex
        self.__array[this] = item

    def __moveDown(self, item: T, this: int) -> None:
        key = self.__keyFunc
        nextIndex = this * 2 + 1
        while nextIndex < self.__count:
            other = nextIndex + 1
            if other < self.__count and \
                    key(self.__array[other]) < key(self.__array[nextIndex]):
                nextIndex = other
            if key(item) <= key(self.__array[nextIndex]):
                break
            self.__array[this] = self.__array[nextIndex]
            this = nextIndex
            nextIndex = this * 2 + 1
        self.__array[this] = item

    def add(self, item: T) -> None:
        """Adds an item to the heap.
        """
        #assert item is not None, 'None is not a valid item to add'
        if self.__array[0] is None:
            self.__moveDown(item, 0)
        else:
            last = self.__count
            self.__count += 1
            if last == len(self.__array):
                self.__array.append(None)
            self.__moveUp(item, last)

    def remove(self, item: T) -> None:
        """Removes an item from the heap.
        Raises ValueError if the heap does not contain the item.
        """
        this = self.__array.index(item, 0, self.__count)
        if this == 0:
            self.__array[0] = None
        else:
            self.__count -= 1
            if this != self.__count:
                item = cast(T, self.__array[self.__count])
                key = self.__keyFunc
                if key(item) > key(self.__array[this]):
                    self.__moveDown(item, this)
                else:
                    self.__moveUp(item, this)

    def peek(self) -> Optional[T]:
        """Returns the smallest item in the heap.
        """
        item = self.__array[0]
        if item is None:
            if self.__count > 1:
                self.__count -= 1
                item = cast(T, self.__array[self.__count])
                self.__moveDown(item, 0)
                return self.__array[0]
            else:
                return None
        else:
            return item

    def __next__(self) -> T:
        """Removes the smallest item from the heap and returns it.
        """
        item = self.peek()
        if item is None:
            raise StopIteration
        else:
            self.__array[0] = None
            return item

    def _check(self, fail: Any = None) -> bool:
        """Check proper element ordering (used for unit testing only).
        """
        key = self.__keyFunc
        if self.__array[0] is not None:
            index = 0
        else:
            index = 1
        while index < self.__count:
            one = index * 2 + 1
            two = index * 2 + 2
            if one < self.__count and \
                    key(self.__array[one]) < key(self.__array[index]) \
            or two < self.__count and \
                    key(self.__array[two]) < key(self.__array[index]):
                if fail is not None:
                    fail.fail('Invalid state at position ' + str(index) +
                        ' of ' + str(self.__count))
                return False
            index += 1
        return True

def escapeURL(text: str) -> str:
    return quote_plus(utf8encode(text)[0])

@contextmanager
def atomicWrite(
        path: str, mode: str, fsync: bool = True, **kwargs: Any
        ) -> Iterator[IO[Any]]:
    '''A context manager to write a file in such a way that in an event of
    abnormal program termination either an old version of the file remains,
    or a new one, but not something inbetween.
    It writes the new data into a temporary file, named like the actual file
    with a ".tmp" suffix appended. When the file is closed, the temporary
    file atomically replaces the actual file.

    'path' must be a string containing the file path to open.
    'mode' is the mode in which the file will be opened; only modes "w" and
    "wb" are supported.
    'fsync' can be set to False to not force changes to be committed to
    long-term storage; this is faster but destroys the atomicity guarantee.
    Other keyword arguments are passed to the builtin open() function.

    Usage:
    with atomicWrite(path, mode) as out:
        out.write(...)

    If there is an uncaught exception in the body of the "with" statement,
    the old version of the file will remain.

    The body of the "with" statement must not close the file. If it does,
    atomicity cannot be guaranteed; this will be treated as an error and
    cause the old version of the file to remain.

    Note that we do not guarantee durability: if the system goes down after
    the context is closed, it is possible the old version of the file will
    remain on storage. The caller must perform a sync on the containing
    directory if durability is required.
    '''

    # Note: We could support more modes, but so far we didn't have a need to.
    if mode not in ('w', 'wb'):
        raise ValueError('invalid mode: %r' % mode)

    tempPath = path + '.tmp'
    try:
        with open(tempPath, mode, **kwargs) as out:
            yield out
            if fsync:
                # Flush Python's buffers.
                out.flush()
                # Flush OS buffers.
                os.fsync(out.fileno())
    except FileNotFoundError:
        # Don't attempt to remove temporary file if it couldn't be created.
        raise
    except: # pylint: disable=bare-except
        # We do actually want to catch all exceptions here.
        try:
            # Clean up temporary file.
            os.remove(tempPath)
        finally:
            # Propagate the original exception, even if the remove fails.
            raise
    else:
        # Move the temporary file over the actual file.
        os.replace(tempPath, path)

class _AbstractField:
    '''Descriptor that declares an abstract field.
    This allows static code checkers to know a property named "a" exists,
    but any attempt to access it will raise an exception.
    Also any attempt to instantiate a class that does not override the
    abstract field will raise an exception.

    Usage:

    from abc import ABC
    from typing import ClassVar

    class AbstractClass(ABC):
        a = abstract # type: ClassVar[str]
        b = 2 # type: int
    '''
    __isabstractmethod__ = True

    def __get__(self, instance, owner):
        if instance is None:
            # Class attribute access.
            return self
        # Note: This is only unreachable if the abstract class fails to
        #       inherit from ABC, but that is an easy mistake to make.
        raise NotImplementedError('Read of abstract field')

    def __set__(self, instance, value):
        raise AttributeError('Write to abstract field')

    def __delete__(self, instance):
        raise AttributeError('Delete of abstract field')

    def __repr__(self):
        return '<abstract field>'

abstract = _AbstractField() # type: Any

def iterable(obj: object) -> bool:
    '''Returns True iff the given object can be iterated through.
    Examples of iterables are sequences and generators.
    Note that 'str' and 'bytes' are not considered iterable.
    '''
    return hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes))

def chop(sequence: Iterable[T], size: int) -> Iterator[Iterable[T]]:
    '''Iterate through a given sequence in chunks of the given size.
    '''
    it = iter(sequence)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            break
        yield chunk

def pluralize(word: str, amount: Union[int, Sized]) -> str:
    '''Returns the given word in singular or plural form, depending on the
    given amount. The amount can an integer or a data structure that supports
    len().
    '''
    if not isinstance(amount, int):
        amount = len(amount)
    # Note: So far this primitive approach is good enough for all words we feed
    #       it.
    return word if amount == 1 else (word + 's')

class ResultKeeper(dict, Mapping[KT, VT]):
    '''A dictionary that will get missing values from a factory function.
    The factory function takes a single argument, which is the key that was
    looked up but not found in the dictionary.
    The typical use is to cache return values of a deterministic function
    without side effects.
    The class collections.defaultdict is similar to this class, but it takes
    a factory function with no arguments instead of passing the requested
    key to the factory function.
    '''

    def __init__(self, factory: Callable[[KT], VT]):
        super().__init__()
        self.factory = factory

    def __missing__(self, key: KT) -> VT:
        value = self.factory(key)
        self[key] = value
        return value

class SharedInstance:
    '''A descriptor that can be used as a class variable which always
    returns the same instance, that is allocated on first use.
    This is only applicable to classes that do not require any arguments
    to their constructor.
    A shared instance is "half a singleton", since it does not guarantee
    there is only one instance of a class.

    Usage:
    class SomeClass:
        instance = SharedInstance()
        def __init__(self):
            ...
        def method(self):
            ...
    SomeClass.instance.method()
    '''
    def __get__(self, obj: Optional[T], cls: Type[T]) -> T:
        # It may seem simpler to store the instance in the descriptor,
        # but that will fail for inheritance: "Subclass.instance" would
        # return "Superclass.instance" if that was already created.
        instance = cls.__dict__.get('__sharedInstance')
        if instance is None:
            instance = cls.__new__(cls)
            instance.__init__()
            # Note: Don't store unless constructor finished successfully.
            setattr(cls, '__sharedInstance', instance)
        return instance

    def __set__(self, obj: Type[T], value: T) -> None:
        raise AttributeError('Shared instances are read-only')

    def __delete__(self, obj: Type[T]) -> None:
        raise AttributeError('Shared instances cannot be deleted')

class SingletonMeta(ABCMeta):
    '''A metaclass to turn a shared instance into a full singleton.

    Usage:
    class SomeSingleton(metaclass=SingletonMeta):
        instance = SharedInstance()
        def __init__(self):
            ...
        def method(self):
            ...
    SomeSingleton.instance.method()
    '''

    def __call__(cls):
        raise TypeError(
            'Direct instantiation of a singleton is not allowed; '
            'use the "instance" class variable instead.'
            )

class _CachedProperty(Generic[C, T]):
    '''Descriptor that implements the `cachedProperty` decorator.
    '''

    def __init__(self, method: Callable[[C], T]):
        self.__method = method
        self.__name = None # type: Optional[str]

    def __get__(self, instance: C, owner: object) -> T:
        if instance is None:
            # Class attribute access.
            # Do the same thing as Python's builtin "property" class:
            # return the descriptor object.
            return self

        name = self.__name
        if name is None:
            self.__name = name = self.__getName(instance)

        try:
            # Return cached value.
            return instance.__dict__[name]
        except KeyError:
            # Compute and store value.
            value = self.__method(instance)
            instance.__dict__[name] = value
            return value

    def __set__(self, instance: C, value: T) -> None:
        raise AttributeError('Cached properties are read-only')

    def __delete__(self, instance: C) -> None:
        raise AttributeError('Cached properties cannot be deleted')

    def __getName(self, instance: C) -> str:
        '''Gets the unique name for storing this property's value.
        '''
        for container in instance.__class__.__mro__:
            for name, member in container.__dict__.items():
                if member is self:
                    # The use of "$" makes this invalid as a Python
                    # identifier, reducing the chance of name collisions.
                    return '$%s$%s' % (container.__name__, name)
        raise AttributeError('Property does not belong to this object')

def cachedProperty(method: Callable[[C], T]) -> _CachedProperty[C, T]:
    '''Decorator that creates a read-only property with the same name
    as the method it wraps. This method is called the first time the
    value of the property is read. On subsequent calls, that same
    value is returned without running the method again. This is useful
    when a value takes some time to compute, but never changes.
    '''
    return _CachedProperty(method)

class MissingValue:
    '''Value that can be used to represent a missing value (null) in
    database records. Unlike None, this can be compared to any value
    type. It is considered larger than any other value, so it will
    end up at the end of sorted lists.
    '''

    def __repr__(self) -> str:
        return 'missing'

    def __str__(self) -> str:
        return 'missing'

    def __eq__(self, other: object) -> bool:
        return self is other

    def __ne__(self, other: object) -> bool:
        return self is not other

    def __lt__(self, other: object) -> bool:
        return False

    def __le__(self, other: object) -> bool:
        return self is other

    def __gt__(self, other: object) -> bool:
        return self is not other

    def __ge__(self, other: object) -> bool:
        return True

missing = MissingValue()

_versionPattern = re.compile(r'(\d+)\.(\d+)\.(\d+)(\D.*)?$')
def parseVersion(versionStr: str) -> Tuple[int, int, int]:
    '''Parses a version string.
    Returns a 3-tuple containing the version numbers.
    Raises ValueError if the version string could not be parsed.
    '''
    match = _versionPattern.match(versionStr)
    if match is None:
        raise ValueError('invalid version format: "%s"' % versionStr)
    else:
        version = cast(Tuple[int, int, int], tuple(
            int(versionComponent)
            for versionComponent in match.group(1, 2, 3)
            ))
        suffix = match.group(4)
        if suffix is not None and suffix.startswith('-pre'):
            try:
                suffixVersion = int(suffix[4 : ])
            except ValueError:
                suffixVersion = 0
            if version[2] == 0:
                # Treat a prerelease version as a very late release from the
                # previous series.
                return ( version[0], version[1] - 1, 9900 + suffixVersion )
            else:
                raise ValueError(
                    'invalid prerelease version: "%s"' % versionStr
                    )
        else:
            return version

def _escapeRegExp(matcher: Match[str]) -> str:
    match = matcher.group(0)
    if match == '*':
        return '.*'
    elif match == '?':
        return '.'
    else:
        return '\\' + match

def wildcardMatcher(pattern: str) -> Pattern[str]:
    return re.compile(
        re.sub(r'[.^$+?{}\\|()*]', _escapeRegExp, pattern)
        + '$'
        )

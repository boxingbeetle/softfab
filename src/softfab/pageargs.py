# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from re import compile as re_compile
from typing import (
    TYPE_CHECKING, AbstractSet, Any, Callable, Collection, Dict, Generic,
    Iterable, Iterator, Mapping, Match, Optional, Sequence, Set, Tuple, Type,
    TypeVar, Union, cast, overload
)
from urllib.parse import parse_qs

from softfab.compat import NoReturn
from softfab.timelib import stringToTime
from softfab.timeview import formatDate, formatTime
from softfab.utils import cachedProperty, escapeURL, iterable

# Avoid circular import.
if TYPE_CHECKING:
    from softfab.request import Request
else:
    Request = None

ArgsT = TypeVar('ArgsT', bound='PageArgs')
ArgsT_co = TypeVar('ArgsT_co', bound='PageArgs', covariant=True)
ValueT = TypeVar('ValueT')
CollectionT = TypeVar('CollectionT', bound=Collection)
DefaultT = TypeVar('DefaultT')
EnumT = TypeVar('EnumT', bound='Enum')

class ParseCorrected(Generic[ValueT], Exception):
    '''Raised by an implementation of Argument.parse() to issue a correction
    to the value of that particular Argument.
    '''

    def __init__(self, correctValue: ValueT):
        Exception.__init__(self)
        self.correctValue = correctValue

class ArgsCorrected(Generic[ArgsT], Exception):
    '''Raised by a Processor to issue a correction to the PageArgs.
    Depending on the type of page, this may be handled as a redirection or
    as an error.
    '''

    def __init__(self, args: ArgsT, **kwargs: object):
        Exception.__init__(self)
        # Note: The Exception base class has an attribute named "args", so we
        #       should use a different name.
        self.correctedArgs = args.override(**kwargs) if kwargs else args

class ArgsInvalid(Exception):
    '''Raised when one or more page arguments are invalid and cannot be
    automatically corrected. This can happen for example if ValueError is
    raised when parsing an Argument, such as parsing "abc" as an integer.
    One ArgsInvalid exception can contain multiple error messages, not just
    the first error.
    The property "errors" is a dictionary that maps argument name to a
    message string describing what was wrong with the value of that argument.
    '''

    def __init__(self) -> None:
        Exception.__init__(self)
        self.errors = {} # type: Dict[str, str]

    def addError(self, name: str, message: str) -> 'ArgsInvalid':
        '''Adds an error message about an invalid argument.
        Returns the exception object itself.
        '''
        assert name not in self.errors
        self.errors[name] = message
        return self

    def __str__(self) -> str:
        return 'Invalid arguments: ' + ', '.join(
            '%s (%s)' % item
            for item in sorted(self.errors.items())
            )

class _ArgumentFactory(Generic[ArgsT]):
    '''Used by a parse method to create a PageArgs (subclass) instance.
    '''

    def __init__(
            self,
            argsClass: Type[ArgsT],
            fields: Mapping[str, Iterable[bytes]]
            ):
        self.__argsClass = argsClass
        self.__data = {} # type: Dict[str, object]
        self.__unclaimedFields, self.__correctedArgs = \
            argsClass._renameArguments(fields) # pylint: disable=protected-access
        self.__invalidArgs = ArgsInvalid()

    def claimField(self,
            key: str, parseFunc: Callable[..., ValueT]
            ) -> Optional[ValueT]:
        fieldValues = self.__unclaimedFields.pop(key)
        try:
            values = [ item.decode('utf-8') for item in fieldValues ]
        except UnicodeDecodeError as ex:
            self.__invalidArgs.addError(key, str(ex))
            return None
        try:
            return parseFunc(*values)
        except ParseCorrected as ex:
            self.__correctedArgs = True
            return cast(ValueT, ex.correctValue)
        except ValueError as ex:
            self.__invalidArgs.addError(key, str(ex))
            return None

    @property
    def unclaimedFields(self) -> AbstractSet[str]:
        return self.__unclaimedFields.keys()

    def store(self, argName: str, value: object) -> None:
        if value is mandatory:
            self.__invalidArgs.addError(
                argName, 'No value was provided for this mandatory argument'
                )
        else:
            self.__data[argName] = value

    def finish(self) -> ArgsT:
        '''Called when parsing is finished.
        Returns the constructed PageArgs instance.
        Raises ArgsInvalid if any errors occurred during parsing.
        Raises ArgsCorrected if any arguments were auto-corrected.
        '''
        argsClass = self.__argsClass

        # Any unclaimed key is an error.
        for key in self.__unclaimedFields.keys():
            if isinstance(getattr(argsClass, key, None), DictArg):
                message = 'Dictionary argument lacks ".<key>"'
            else:
                message = 'There is no argument by this name'
            self.__invalidArgs.addError(key, message)
        if self.__invalidArgs.errors:
            raise self.__invalidArgs

        args = argsClass(**self.__data)
        if self.__correctedArgs:
            raise ArgsCorrected(args)
        else:
            return args

class PageArgs:
    '''Each Page should contain a reference to a subclass of PageArgs,
    which contains the arguments that the Page accepts.

    The arguments are defined as class-scope fields like this:
        class Arguments(PageArgs):
            default = StrArg('default value')
            mandatory = StrArg()
            computed = StrArg(dynamic)
            repeat = IntArg(1)

    No default value specified means that the argument is mandatory.
    If you have to determine the default value dynamically, you should use
    the "dynamic" object as the default value and in your Processor compute
    the actual value and raise ArgsCorrected.
    '''

    @classmethod
    def _renameArguments(
            cls, fields: Mapping[str, Iterable[bytes]]
            ) -> Tuple[Dict[str, Iterable[bytes]], bool]:
        # Compute mapping from old to new names.
        nameMapping = {} # type: Dict[str, str]
        for container in cls.__mro__:
            for oldName, member in container.__dict__.items():
                if isinstance(member, RenameToArg):
                    # Renames in subclasses override those in superclasses.
                    if oldName not in nameMapping:
                        nameMapping[oldName] = member.newName

        # Apply mapping from old to new names.
        newFields = {}
        correctedArgs = False
        for name, value in fields.items():
            # Transitively look up new names until the most recent name is
            # found.
            while name in nameMapping:
                correctedArgs = True
                name = nameMapping[name]
                if name in fields:
                    # If a value is provided for the newer name, ignore the
                    # value provided for the older name.
                    break
            else:
                newFields[name] = value
        return newFields, correctedArgs

    @classmethod
    def _iterArguments(cls) -> Iterator[Tuple[str, 'Argument']]:
        '''Iterates through all arguments in this PageArgs class.
        Each item is a tuple of the argument name and its Argument subclass.
        '''
        overridden = set() # type: Set[str]
        for container in cls.__mro__:
            for name, member in container.__dict__.items():
                if isinstance(member, Argument):
                    if name not in overridden:
                        overridden.add(name)
                        yield name, member

    @classmethod
    def keys(cls) -> Iterator[str]:
        '''Iterates through the argument names.
        '''
        for name, member_ in cls._iterArguments():
            yield name

    @classmethod
    def iterMandatoryArgs(cls) -> Iterator[str]:
        '''Iterates through the names of the mandatory arguments.
        '''
        for name, member in cls._iterArguments():
            if member.default is mandatory:
                yield name

    @classmethod
    def isArgument(cls, name: str) -> bool:
        '''Returns True if an argument with the given name exists,
        returns False if a non-argument attribute with the given name exists
        and raises AttributeError if no attribute with the given name exists.
        '''
        return isinstance(getattr(cls, name), Argument)

    @classmethod
    def subset(cls: Type[ArgsT], args: 'PageArgs') -> ArgsT:
        '''Creates a PageArgs instance which contains a subset of the given
        arguments.
        All mandatory arguments in this class must be present in the given
        arguments object.
        '''
        if not isinstance(args, PageArgs):
            raise TypeError(
                f'"{type(args).__name__}" does not inherit from PageArgs'
                )
        return cls(**{
            name: args.__dict__[name]
            for name, member_ in cls._iterArguments()
            })

    @classmethod
    def parse(
            cls: Type[ArgsT],
            fields: Mapping[str, Iterable[bytes]],
            req: Optional[Request] = None
            ) -> ArgsT:
        '''Creates a PageArgs instance with values parsed from the given
        fields.
        The "fields" argument must be a mapping, where the keys match the
        argument names and the values are sequences of strings (this matches
        Twisted's Request.args).
        The "req" argument can be provided to initialise any RefererArgs from.
        Raises ArgsCorrected if any of the parse methods performed a
        correction on the parsed values.
        '''
        factory = _ArgumentFactory(cls, fields)
        for argName, member in cls._iterArguments():
            if isinstance(member, DictArg):
                topLevelItems = {} # type: Dict[str, object]
                # Filter out the fields that belong to the dictionary.
                # We claim fields during iteration, which invalidates the
                # unclaimed fields iterator, so make a copy.
                for key in list(factory.unclaimedFields):
                    match = member.match(key)
                    if match:
                        groups = match.groups()
                        if groups[0] == argName:
                            items = topLevelItems
                            for group in groups[1 : -1]:
                                items = cast(
                                    Dict[str, object],
                                    items.setdefault(group, {})
                                    )
                            items[groups[-1]] = factory.claimField(
                                key, member.parse
                                )
                value = DictArgInstance(topLevelItems) # type: object
            else:
                try:
                    value = factory.claimField(argName, member.parse)
                except KeyError:
                    # No value in request: use default.
                    if req is not None and isinstance(member, RefererArg) \
                    and req.refererPage == member.getPage():
                        value = req.refererQuery
                    else:
                        value = member.default
            # Store the parsed value.
            factory.store(argName, value)
        return factory.finish()

    def __init__(self,
            *vargs: Union[Mapping[str, object], 'PageArgs'],
            **kwargs: object
            ):
        '''Creates a PageArgs instance corresponding to the given values.
        Positional arguments must be mappings, such as `PageArgs` or `dict`.
        If more than one value is given for the same argument, the last value
        is used.
        Raises KeyError if a non-existing argument is passed or if a mandatory
        argument is omitted.
        Raises TypeError if a value's type does not match the corresponding
        argument's type.
        '''

        # Merge the given argument objects (if any) into kwargs.
        for args in reversed(vargs):
            for name, value in args.items():
                kwargs.setdefault(name, value)

        # Note: This is similar to Request._parse(), but not similar enough
        #       to make it worthwhile to use a shared implementation.
        # Initialize all Arguments.
        for name, member in self._iterArguments():
            default = member.default
            if name in kwargs:
                value = kwargs.pop(name) # claim key
                # Note: The default value is accepted even if it is not of a
                #       value type that is usually accepted by this argument.
                #       This allows for example None only on StrArgs which
                #       have None as the default value.
                if value == default:
                    if isinstance(member, DictArg):
                        assert isinstance(value, dict), value
                        value = DictArgInstance(value)
                    else:
                        # Note: Even though the value is equal to the default,
                        #       it might be of a different type. For example
                        #       a 'set' can be equal to a 'frozenset', but we
                        #       don't want to store a mutable value.
                        value = default
                else:
                    try:
                        value = member.convert(value)
                    except TypeError as ex:
                        raise TypeError(
                            f'bad value type "{type(value).__name__}" '
                            f'for argument "{name}": {ex}'
                            ) from ex
            else:
                # No value in request: use default.
                if default is mandatory:
                    raise KeyError(f'missing argument: {name}')
                else:
                    value = default
            self.__dict__[name] = value

        # Any unclaimed key is an error.
        for key in kwargs:
            raise KeyError(f'no such argument: {key}')

    def __repr__(self) -> str:
        cls = self.__class__
        def presentValue(key: str, value: object) -> object:
            if isinstance(value, str):
                if isinstance(getattr(cls, key), PasswordArg):
                    return '<password>'
                else:
                    return repr(value)
            else:
                return value
        return '%s(%s)' % (cls.__name__, ', '.join(
            f'{key}={presentValue(key, value)}'
            for key, value in sorted(self.items())
            ))

    def items(self) -> Iterator[Tuple[str, object]]:
        '''Iterates through the arguments, one key/value pair at a time.
        '''
        for name, member_ in self._iterArguments():
            yield name, self.__dict__[name]

    def valueForWidget(self, name: str) -> object:
        """Return the argument value for widget `name`.
        Raises KeyError if there is no argument that matches `name`
        or it is a non-existing path in a dictionary argument.
        """
        argDecl = getattr(self.__class__, name, None)
        if isinstance(argDecl, Argument):
            return self.__dict__[name]
        for argName, member in self._iterArguments():
            if isinstance(member, DictArg):
                match = member.match(name)
                if match:
                    groups = match.groups()
                    if groups[0] == argName:
                        value = self.__dict__[argName]
                        for group in groups[1:]:
                            if not isinstance(value, DictArgInstance):
                                raise KeyError(name)
                            value = value[group]
                        if isinstance(value, DictArgInstance):
                            raise KeyError(name)
                        return value
        raise KeyError(name)

    def defaultForWidget(self, name: str) -> object:
        """Return the default value for widget `name`.
        Raises KeyError if there is no argument that matches `name`.
        """
        argDecl = getattr(self.__class__, name, None)
        if isinstance(argDecl, Argument):
            return argDecl.default
        for argName_, member in self._iterArguments():
            if isinstance(member, DictArg) and member.match(name):
                return member.default
        raise KeyError(name)

    def externalize(self) -> Iterator[Tuple[str, Sequence[str]]]:
        """Iterates through string representations of the non-default
        values of the arguments.
        """
        for name, member in self._iterArguments():
            value = self.__dict__[name]
            if isinstance(member, DictArg):
                yield from member.externalize(name, value)
            elif value != member.default:
                yield name, _externalizeArg(member, value)

    def override(self: ArgsT, **kwargs: object) -> ArgsT:
        '''Creates a copy of this PageArgs object, with given values
        replacing the original values.
        '''
        keyValues = dict(self.items())
        keyValues.update(kwargs)
        return self.__class__(**keyValues)

    @cachedProperty
    def refererName(self) -> Optional[str]:
        '''The name of the page that refered to our page,
        or None if we have no RefererArg with a value.
        '''
        for name, member in self._iterArguments():
            if isinstance(member, RefererArg):
                query = self.__dict__[name]
                if query is not None:
                    return member.getPage()
        return None

    @cachedProperty
    def refererURL(self) -> Optional[str]:
        '''The URL (including query) of the page that refered to our page,
        or None if we have no RefererArg with a value.
        '''
        for name, member in self._iterArguments():
            if isinstance(member, RefererArg):
                values = self.__dict__
                query = values[name]
                if query is not None:
                    sharedValues = {
                        sharedName: values[sharedName]
                        for sharedName in member.shared
                        }
                    return f'{member.getPage()}?' \
                           f'{query.override(**sharedValues).toURL()}'
        return None

class _MandatoryValue:
    '''Use this as a default value for an Argument to indicate that the
    argument is mandatory: requests without the argument are not accepted.
    '''

    def __str__(self) -> str:
        return '<mandatory argument value>'

mandatory = _MandatoryValue()

class _DynamicValue:
    '''Use this as a default value for an Argument to indicate that the
    default value is dynamic: requests without the argument are passed into
    processing with the value "dynamic". The process() method must react
    to this by raising ArgsCorrected.
    '''

    def __str__(self) -> str:
        return '<dynamic argument value>'

dynamic = _DynamicValue()

class Argument(Generic[ValueT, DefaultT]):
    '''Superclass for page arguments.
    A page argument is an input passed to a page when it is requested,
    similar to a function call argument.
    '''

    @overload
    def __init__(self, default: DefaultT
                 ): # pylint: disable=unused-argument
        ...

    @overload
    def __init__(self, default: _DynamicValue
                 ): # pylint: disable=unused-argument
        ...

    @overload
    def __init__(self, default: _MandatoryValue = mandatory
                 ): # pylint: disable=unused-argument
        ...

    def __init__(self, default: Any = mandatory):
        '''Creates a page argument with a given default value.
        '''
        self.__default = default
        self.__name = None # type: Optional[str]

    def __eq__(self, other: object) -> bool:
        '''Arguments are considered equal if they are of the same type.
        Defaults may differ per page and are not considered in equality.
        Since the name is not part of the argument object itself,
        it cannot be considered in equality.
        '''
        if isinstance(other, Argument):
            return type(self) is type(other) and self._sameArg(other)
        else:
            return NotImplemented

    def _sameArg(self, other: 'Argument') -> bool:
        '''Return True iff the `other` argument, which is of the same type
        as this one, is considered equal to this.
        '''
        raise NotImplementedError

    @overload
    def __get__(self,
            instance: None, owner: Type[PageArgs]
            ) -> 'Argument[ValueT, DefaultT]':
        ...

    @overload
    def __get__(self,
            instance: PageArgs, owner: Type[PageArgs]
            ) -> Union[ValueT, DefaultT]:
        ...

    def __get__(self,
                instance: Optional[PageArgs],
                owner: Type[PageArgs]
                ) -> Any:
        if instance is None:
            # Class attribute access.
            return self
        else:
            return instance.__dict__[self.__getName(instance)]

    def __set__(self,
            instance: 'Argument[ValueT, DefaultT]',
            value: ValueT
            ) -> NoReturn:
        raise AttributeError('Page arguments are read-only')

    def __delete__(self,
            instance: 'Argument[ValueT, DefaultT]'
            ) -> NoReturn:
        raise AttributeError('Page arguments cannot be deleted')

    def __getName(self, obj: PageArgs) -> str:
        if self.__name is None:
            for name, member in (
                obj._iterArguments() # pylint: disable=protected-access
                ):
                if member is self:
                    self.__name = name
                    break
            else:
                raise AttributeError(
                    'property does not belong to this object'
                    )
        return self.__name

    @property
    def default(self) -> DefaultT:
        return self.__default

    def parse(self, *strValues: str) -> Union[ValueT, DefaultT]:
        '''Converts string representation(s) of a value to the corresponding
        value in the proper type.
        The returned value must be immutable.
        '''
        raise NotImplementedError

    def convert(self, value: Any) -> ValueT:
        '''Converts the given value to a value suitable for storing
        in the PageArgs object. If the value is of the wrong type,
        TypeError is raised. Implementations of this method can be very
        selective in the types they support. For example, although it is
        possible to convert from string to integer for some strings,
        there is no need to do that conversion.
        '''
        raise NotImplementedError

class SingularArgument(Argument[ValueT, DefaultT]):
    '''Argument which consists of a single value, as opposed to a sequence.
    '''

    def _sameArg(self, other: Argument) -> bool:
        return True

    def parse(self, *strValues: str) -> Union[ValueT, DefaultT]:
        if len(strValues) == 1:
            return self.parseValue(*strValues)
        else:
            raise ValueError('%d values were provided, expected %s' % (
                len(strValues),
                '1' if self.default is mandatory else '0 or 1'
                ))

    def parseValue(self, strValue: str) -> Union[ValueT, DefaultT]:
        '''Converts string representation of a value to the corresponding
        value in the proper type.
        The returned value must be immutable.
        '''
        raise NotImplementedError

    def externalize(self, value: ValueT) -> str:
        '''Converts a value to its string representation.
        It should be done such that parse(externalize(value)) == value.
        '''
        raise NotImplementedError

class _StrArg(SingularArgument[str, DefaultT]):
    '''Argument whose value is a string.
    Leading and trailing spaces are stripped.
    '''

    def parseValue(self, strValue: str) -> str:
        for ch in strValue:
            if ord(ch) < 32 and ch not in '\t\n\r':
                raise ValueError(
                    'Control character 0x%02X not allowed in strings' % ord(ch)
                    )
        stripped = strValue.strip()
        if stripped != strValue:
            raise ParseCorrected(stripped)
        return strValue

    def externalize(self, value: str) -> str:
        return value

    def convert(self, value: str) -> str:
        if isinstance(value, str):
            return value
        else:
            raise TypeError('value is not a string')

if TYPE_CHECKING:
    @overload
    def StrArg() -> _StrArg[str]:
        ...

    @overload
    def StrArg( # pylint: disable=function-redefined
            default: DefaultT
            # pylint: disable=unused-argument
            ) -> _StrArg[DefaultT]:
        ...

    def StrArg( # pylint: disable=function-redefined
            default=mandatory
            # pylint: disable=unused-argument
            ):
        pass
else:
    StrArg = _StrArg

class PasswordArg(_StrArg[str]):
    '''Argument whose value is a password string.
    '''

    def __init__(self) -> None: # pylint: disable=useless-super-delegation
        super().__init__()

    def parseValue(self, strValue: str) -> str:
        for ch in strValue:
            if ord(ch) < 32:
                raise ValueError('Control characters not allowed in passwords')
        return strValue

class BoolArg(SingularArgument[bool, bool]):
    '''Argument whose value is a Boolean.
    '''

    def __init__(self) -> None:
        super().__init__(False)

    def parseValue(self, strValue: str) -> bool:
        lowerValue = strValue.lower()
        if lowerValue == 'true':
            return True
        elif lowerValue == 'false':
            return False
        else:
            raise ValueError(strValue)

    def externalize(self, value: bool) -> str:
        return str(value).lower()

    def convert(self, value: bool) -> bool:
        if isinstance(value, bool):
            return value
        else:
            raise TypeError('value is not a boolean')

class _EnumArg(SingularArgument[EnumT, DefaultT]):
    '''Argument whose value is part of an enumeration.
    '''

    def __init__(self,
            enumType: Type[EnumT],
            default: Union[DefaultT, _MandatoryValue] = mandatory
            ):
        assert issubclass(enumType, Enum)
        assert default is None or default is mandatory \
            or isinstance(default, enumType)
        super().__init__(default)
        self.__enumType = enumType

    def _sameArg(self, other: Argument) -> bool:
        # pylint: disable=protected-access
        return self.__enumType == cast(_EnumArg, other).__enumType

    def parseValue(self, strValue: str) -> EnumT:
        if strValue:
            try:
                return self.__enumType.__members__[strValue.upper()]
            except KeyError as ex:
                raise ValueError('got "%s", expected one of %s' % (
                    strValue.lower(),
                    ', '.join(
                        f'"{name.lower()}"'
                        for name in self.__enumType.__members__
                        ),
                    )) from ex
        else:
            raise ValueError('empty value not allowed')

    def externalize(self, value: EnumT) -> str:
        return value.name.lower()

    def convert(self, value: EnumT) -> EnumT:
        if isinstance(value, self.__enumType):
            return value
        elif isinstance(value, Enum):
            raise TypeError(
                f'value is of the wrong Enum type: '
                f'expected "{self.__enumType.__name__}", '
                f'got "{type(value).__name__}"'
                )
        else:
            raise TypeError('value is not an Enum')

if TYPE_CHECKING:
    @overload
    def EnumArg(
            enumType: Type[EnumT],
            # pylint: disable=unused-argument
            ) -> _EnumArg[EnumT, EnumT]:
        ...

    @overload
    def EnumArg( # pylint: disable=function-redefined
            enumType: Type[EnumT],
            default: DefaultT
            # pylint: disable=unused-argument
            ) -> _EnumArg[EnumT, DefaultT]:
        ...

    def EnumArg( # pylint: disable=function-redefined
            default=mandatory
            # pylint: disable=unused-argument
            ):
        pass
else:
    EnumArg = _EnumArg

class _IntArg(SingularArgument[int, DefaultT]):
    '''Argument whose value is an integer.
    '''

    def parseValue(self, strValue: str) -> int:
        return int(strValue)

    def externalize(self, value: int) -> str:
        return str(value)

    def convert(self, value: int) -> int:
        if isinstance(value, int):
            return value
        else:
            raise TypeError('value is not an integer')

if TYPE_CHECKING:
    @overload
    def IntArg() -> _IntArg[int]:
        ...

    @overload
    def IntArg( # pylint: disable=function-redefined
            default: DefaultT
            # pylint: disable=unused-argument
            ) -> _IntArg[DefaultT]:
        ...

    def IntArg( # pylint: disable=function-redefined
            default=mandatory
            # pylint: disable=unused-argument
            ):
        pass
else:
    IntArg = _IntArg

class DateArg(SingularArgument[int, Optional[int]]):
    '''Argument whose value is a date.
    '''

    def __init__(self,
            default: Union[None, int, _MandatoryValue] = mandatory,
            roundUp: bool = False
            ):
        super().__init__(default)
        self.__roundUp = roundUp

    def _sameArg(self, other: Argument) -> bool:
        # pylint: disable=protected-access
        return self.__roundUp == cast(DateArg, other).__roundUp

    def parseValue(self, strValue: str) -> Optional[int]:
        if strValue:
            # TODO: This will parse date + time strings as well.
            #       When fixing this, make sure DateTimeArg is changed too.
            return stringToTime(strValue, self.__roundUp)
        elif self.default is mandatory:
            raise ValueError('empty value not allowed')
        else:
            return None

    def externalize(self, value: Optional[int]) -> str:
        return formatDate(value)

    def convert(self, value: int) -> int:
        if isinstance(value, int):
            return value
        else:
            raise TypeError('value is not an integer')

class DateTimeArg(DateArg):
    '''Argument whose value is a date and a time.
    '''

    def externalize(self, value: Optional[int]) -> str:
        return formatTime(value)

class SortArg(SingularArgument[Sequence[str], Sequence[str]]):
    '''Argument that determines the sort order of a DataTable.
    '''

    def __init__(self) -> None:
        default = ()
        super().__init__(default)

    def parseValue(self, strValue: str) -> Sequence[str]:
        return tuple(strValue.split())

    def externalize(self, value: Sequence[str]) -> str:
        return ' '.join(value)

    def convert(self, value: Iterable[str]) -> Sequence[str]:
        if iterable(value):
            return tuple(value)
        else:
            raise TypeError('value is not iterable')

class CollectionArg(Argument[CollectionT, CollectionT],
                    Generic[CollectionT, ValueT]):
    '''Abstract base class for an argument that keeps multiple values.
    '''

    def __init__(self,
            prototype: SingularArgument[ValueT, ValueT] =
                cast(SingularArgument[ValueT, ValueT], StrArg()),
            allowEmpty: bool = True
            ):
        self.__prototype = prototype
        default = (
            self._createValue(()) if allowEmpty else mandatory
            ) # type: Union[CollectionT, _MandatoryValue]
        super().__init__(default)

    def _createValue(self, items: Iterable[ValueT]) -> CollectionT:
        '''Subclasses must implement this to return a value object
        of the right type that contains `items`.
        '''
        raise NotImplementedError

    def _sameArg(self, other: Argument) -> bool:
        # pylint: disable=protected-access
        return self.__prototype == cast(CollectionArg, other).__prototype

    def parse(self, *strValues: str) -> CollectionT:
        parse = self.__prototype.parseValue
        return self._createValue(parse(strValue) for strValue in strValues)

    def externalize(self, value: CollectionT) -> Sequence[str]:
        externalize = self.__prototype.externalize
        return [ externalize(item) for item in value ]

    def convert(self, value: Iterable[ValueT]) -> CollectionT:
        if iterable(value):
            return self._createValue(value)
        else:
            raise TypeError('value is not iterable')

class _ListArg(CollectionArg[Sequence[ValueT], ValueT]):
    '''Argument that keeps a list of values in the same order that
    they were in the request.
    Since arguments are immutable, the actual values are stored in
    a tuple instead of a list.
    '''

    def _createValue(self, items: Iterable[ValueT]) -> Sequence[ValueT]:
        return tuple(items)

if TYPE_CHECKING:
    @overload
    def ListArg(
            prototype: _StrArg[str] = StrArg(),
            allowEmpty: bool = True
            # pylint: disable=unused-argument
            ) -> _ListArg[str]:
        ...

    @overload
    def ListArg( # pylint: disable=function-redefined
            prototype: SingularArgument[ValueT, DefaultT],
            allowEmpty: bool = True
            # pylint: disable=unused-argument
            ) -> _ListArg[ValueT]:
        ...

    def ListArg(): # pylint: disable=function-redefined
        pass
else:
    ListArg = _ListArg

class _SetArg(CollectionArg[AbstractSet[ValueT], ValueT]):
    '''Argument that keeps a set of values in no particular order;
    duplicates are removed.
    If no default value is specified, the set for this argument will
    be empty if the argument doesn't occur in the query. The default
    value can be set to 'mandatory' to refuse empty sets, or to
    a non-empty set to make that the default set.
    Since arguments are immutable, the actual values are stored in
    a frozenset.
    '''

    def _createValue(self, items: Iterable[ValueT]) -> AbstractSet[ValueT]:
        return frozenset(items)

    # https://github.com/PyCQA/pylint/issues/2377
    def parse(self, *strValues: str) -> AbstractSet[ValueT]: # pylint: disable=unsubscriptable-object,useless-suppression
        values = super().parse(*strValues)
        if len(values) == len(strValues):
            return values
        else:
            # Duplicate values were discarded.
            raise ParseCorrected(values)

if TYPE_CHECKING:
    @overload
    def SetArg(
            prototype: _StrArg[str] = StrArg(),
            allowEmpty: bool = True
            # pylint: disable=unused-argument
            ) -> _SetArg[str]:
        ...

    @overload
    def SetArg( # pylint: disable=function-redefined
            prototype: SingularArgument[ValueT, DefaultT],
            allowEmpty: bool = True
            # pylint: disable=unused-argument
            ) -> _SetArg[ValueT]:
        ...

    def SetArg(): # pylint: disable=function-redefined
        pass
else:
    SetArg = _SetArg

# Work around mypy bug by omitting type argument:
#   https://github.com/python/mypy/issues/6730
DictValue = Union[ValueT, 'DictArgInstance']
#DictValue = Union[ValueT, 'DictArgInstance[ValueT]']

class DictArg(Argument[DictValue[ValueT], DictValue[ValueT]]):

    def __init__(self,
            element: Argument[ValueT, ValueT],
            separators: str = '.'
            ):
        if isinstance(element, DictArg):
            raise TypeError('element type cannot be another dictionary')
        empty = {} # type: Mapping[str, DictValue[ValueT]]
        super().__init__(DictArgInstance(empty))
        self.__element = element
        self.__separators = separators
        pattern = ''
        for separator in separators:
            pattern += f'([^{separator}]*)[{separator}]'
        pattern += '(.*)'
        self.__pattern = re_compile(pattern)

    def _sameArg(self, other: Argument) -> bool:
        return ( # pylint: disable=protected-access
            self.__separators == cast(DictArg, other).__separators and
            self.__element == cast(DictArg, other).__element
            )

    def parse(self, *strValues: str) -> ValueT:
        '''Lets the element type parse the given value(s).
        '''
        return self.__element.parse(*strValues)

    def match(self, key: str) -> Optional[Match[str]]:
        return self.__pattern.match(key)

    def convert(self,
             value: Mapping[str, DictValue[ValueT]]
             ) -> 'DictArgInstance[ValueT]':
        if isinstance(value, DictArgInstance):
            return value
        elif isinstance(value, dict):
            return DictArgInstance(value)
        else:
            raise TypeError('value is not a dictionary')

    def externalize(self,
            name: str, value: DictValue[ValueT]
            ) -> Iterator[Tuple[str, Union[str, Sequence[str]]]]:
        element = self.__element
        default = element.default
        for fullName, subValue in _expandNames(name, value, self.__separators):
            if subValue != default:
                yield fullName, _externalizeArg(element, subValue)

def _expandNames(
        prefix: str, value: DictValue[ValueT], separators: str
        ) -> Iterator[Tuple[str, ValueT]]:
    if isinstance(value, DictArgInstance):
        for subkey, subvalue in value.items():
            yield from _expandNames(
                prefix + separators[0] + subkey,
                subvalue,
                separators[1 : ]
                )
    else:
        yield prefix, value

class DictArgInstance(Dict[str, DictValue[ValueT]]):
    '''Stores the values for a DictArg and offers a mapping interface
    to read them.
    Writing is not supported, since Arguments are supposed to be read-only.
    '''

    def __init__(self, items: Mapping[str, DictValue[ValueT]]):
        dict.__init__(self)
        for key, value in items.items():
            if isinstance(value, dict):
                value = DictArgInstance(value)
            dict.__setitem__(self, key, value)

    def __delitem__(self, key: str) -> NoReturn:
        raise TypeError('attempt to modify read-only dictionary')

    def __setitem__(self, key: str, value: Any) -> NoReturn:
        raise TypeError('attempt to modify read-only dictionary')

    def clear(self) -> NoReturn:
        raise TypeError('attempt to modify read-only dictionary')

    def pop(self, key: str, default: Any = ...) -> NoReturn:
        raise TypeError('attempt to modify read-only dictionary')

    def popitem(self) -> NoReturn:
        raise TypeError('attempt to modify read-only dictionary')

    def setdefault(self, key: str, default: Any = ...) -> NoReturn:
        raise TypeError('attempt to modify read-only dictionary')

    def update(self, *d: Any, **kwargs: Any) -> NoReturn:
        raise TypeError('attempt to modify read-only dictionary')

class Query:
    """The query part of a URL.

    Instances of this class are immutable.
    """

    @classmethod
    def fromArgs(cls, args: PageArgs) -> 'Query':
        """Creates a query from page arguments.
        """
        return cls(dict(args.externalize()))

    def __init__(self, data: Mapping[str, Sequence[str]]):
        self._data = data

    def __bool__(self) -> bool:
        return bool(self._data)

    def __str__(self) -> str:
        return self.toURL()

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self._data!r})'

    def override(self,
            *args: PageArgs,
            **kwargs: Union[None, str, Sequence[str]]
            ) -> 'Query':
        """Return this query, with the given arguments replaced.

        If an argument exists in both `args` and `kwargs`, the value from
        `kwargs` is used.

        A `None` replacement removes the argument from the query, if it exists.
        A `str` replacement is treated as a sequence of length 1.
        """

        # Merge overrides.
        override = {} # type: Dict[str, Union[None, str, Sequence[str]]]
        for pageArgs in args:
            override.update(pageArgs.externalize())
        override.update(kwargs)

        # Apply overrides to this query.
        data = dict(self._data)
        for key, value in override.items():
            if value is None:
                data.pop(key, None)
            elif isinstance(value, str):
                data[key] = (value,)
            else:
                data[key] = value
        return self.__class__(data)

    def toURL(self) -> str:
        """Encodes this query to a string that can be appened to a URL.
        """
        return '&'.join(
            f'{escapeURL(key)}={escapeURL(value)}'
            for key, values in self._data.items()
            for value in values
            )

class QueryArg(SingularArgument[Query, None]):
    '''Stores an arbitrary query as a single argument.
    This can be used for example to preserve navigation state when a page
    links or redirects back to its referer.

    A query is a sequence of key-value pairs, where a value can be a single
    string or a sequence of strings.

    The `shared` constructor argument lists names of arguments that are
    shared between the PageArgs containing this QueryArg and the query.
    The shared arguments will be omitted from the stored query. They can
    be specified by name or by PageArgs subclass.
    '''

    def __init__(self, *,
            shared: Union[None, Type[PageArgs], Iterable[str]] = None
            ):
        super().__init__(None)
        if shared is None:
            sharedNames = () # type: Iterable[str]
        elif isinstance(shared, type):
            if issubclass(shared, PageArgs):
                sharedNames = shared.keys()
            else:
                raise TypeError(type(shared))
        else:
            sharedNames = shared
        self.__shared = frozenset(sharedNames)

    @property
    def shared(self) -> AbstractSet[str]:
        return self.__shared

    def _sameArg(self, other: Argument) -> bool:
        # pylint: disable=protected-access
        return self.__shared == cast(QueryArg, other).__shared

    def parseValue(self, strValue: str) -> Query:
        data = parse_qs(strValue, keep_blank_values=True)
        for name in self.__shared:
            data.pop(name, None)
        return Query(data)

    def externalize(self, value: Optional[Query]) -> str:
        assert value is not None
        return value.toURL()

    def convert(self, value: Query) -> Query:
        if isinstance(value, Query):
            return value
        else:
            raise TypeError('value is not a query')

class RefererArg(QueryArg):
    '''Stores a query from a refering page.
    This can be used for example to preserve navigation state when a page
    links or redirects back to its referer.
    '''

    def __init__(self,
            page: str, *,
            shared: Union[None, Type[PageArgs], Iterable[str]] = None
            ):
        QueryArg.__init__(self, shared=shared)
        self.__page = page

    def _sameArg(self, other: Argument) -> bool:
        return ( # pylint: disable=protected-access
            self.__page == cast(RefererArg, other).__page and
            super()._sameArg(other)
            )

    def getPage(self) -> str:
        return self.__page

class RenameToArg:
    '''Provides an easy way to rename an argument.

    Usage:
        class Arguments(PageArgs):
            newArg = StrArg('default')
            oldArg = RenameToArg('newArg')

    It is possible to make a chain for renames: if "a" renames to "b" and
    "b" renames to "c", "a" is renamed to "c".
    '''

    def __init__(self, newName: str):
        self.__newName = newName

    @property
    def newName(self) -> str:
        return self.__newName

@overload
def _externalizeArg(arg: SingularArgument[ValueT, DefaultT],
                    value: ValueT
                    # pylint: disable=unused-argument
                    ) -> Sequence[str]:
    ...

@overload
def _externalizeArg(arg: CollectionArg[Collection[ValueT], ValueT],
                    value: Collection[ValueT]
                    # pylint: disable=unused-argument
                    ) -> Sequence[str]:
    ...

@overload
def _externalizeArg(arg: Any, value: Any # pylint: disable=unused-argument
                    ) -> Sequence[str]:
    # Calling with this signature raises TypeError, but omitting this
    # signature means the calling code has to duplicate the runtime
    # type checks we do here just to please mypy.
    ...

def _externalizeArg(arg: Any, value: Any) -> Sequence[str]:
    if isinstance(arg, SingularArgument):
        return (arg.externalize(value),)
    elif isinstance(arg, CollectionArg):
        return arg.externalize(value)
    else:
        raise TypeError(type(arg))

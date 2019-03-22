# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from enum import Enum
from typing import (
    IO, Callable, ClassVar, Dict, Generic, Iterable, Iterator, List, Mapping,
    Optional, Sequence, Type, TypeVar, Union, cast
)
from xml.sax import make_parser
from xml.sax.handler import (
    ContentHandler, ErrorHandler, feature_external_ges, feature_external_pes,
    feature_string_interning, property_interning_dict
)

from softfab.utils import abstract
from softfab.xmlgen import XML, XMLAttributeValue, XMLContent, xml as xmlnode

# XML parsing:

# Attributes includes more than a mapping interface, but this is the subset
# that we use. The Attributes interface exists only in documentation, not
# in code. The implementation is xml.sax.xmlreader.AttributesImpl, but the
# current type stubs for that are too minimal.
Attributes = Mapping[str, str]

class ParseError(Exception):
    pass

class _XMLHandler(ContentHandler):

    def __init__(self, factory: object):
        ContentHandler.__init__(self)

        # Initial values are just to satisfy the type checker.
        self.__text = False
        self.__content = ''

        self.__nameStack = [] # type: List[str]
        self.__objectStack = [] # type: List[object]
        self.__push('(root)', factory, False)
        self.__parsed = None # type: object

    def __peek(self) -> object:
        return self.__objectStack[-1]

    def __push(self, name: str, obj: object, text: bool) -> None:
        self.__nameStack.append(name)
        self.__objectStack.append(obj)
        self.__text = text

    def __pop(self) -> None:
        self.__nameStack[-1:] = []
        self.__objectStack[-1:] = []
        self.__text = False # nested tags means no text

    def __getContext(self) -> str:
        return '.'.join(self.__nameStack[1:])

    def __getMethod(self, baseName: str, tagName: str = '') -> Callable:
        return getattr(self.__peek(), baseName + tagName.capitalize(), None)

    def getParsed(self) -> object:
        return self.__parsed

    def startElement(self, name: str, attrs: Attributes) -> None:
        # Note: Content containing elements is not supported.
        self.__content = ''

        if self.__parsed is None: # root element?
            factoryMethod = self.__getMethod('create', name)
            if factoryMethod:
                newObj = factoryMethod(dict(attrs))
                self.__parsed = newObj
                self.__push(name, newObj, False)
            else:
                raise ParseError('no factory for tag "%s"' %  name)
        else:
            method = self.__getMethod('_add', name) \
                or self.__getMethod('_set', name)
            if method:
                newObj = method(dict(attrs))
                self.__push(name, newObj, False)
            elif self.__getMethod('_text', name):
                self.__push(name, None, True)
            else:
                objClass = self.__peek().__class__
                className = objClass.__module__ + '.' + objClass.__name__
                raise ParseError(
                    'class "%s" has no parse method for tag "%s" (in %s)'
                    % ( className, name, self.__getContext() )
                    )

    def endElement(self, name: str) -> None:
        if self.__text:
            content = self.__content.strip()
            self.__pop()
            self.__getMethod('_text', name)(content)
        else:
            method = self.__getMethod('_endParse')
            if method:
                method()
            self.__pop()
        self.__content = ''

    def characters(self, content: str) -> None:
        if content and not self.__text and not content.isspace():
            raise ParseError(
                'node %s is not supposed to contain text but contains "%s"'
                % ( self.__getContext(), content )
                )
        self.__content += content

_errorHandler = ErrorHandler()

_interningDict = {} # type: Dict[str, str]

# XML tag class:

class XMLTag(ABC):
    tagName = abstract # type: ClassVar[str]
    boolProperties = () # type: ClassVar[Sequence[str]]
    intProperties = () # type: ClassVar[Sequence[str]]
    enumProperties = {} # type: ClassVar[Mapping[str, Type[Enum]]]

    @classmethod
    def _findDeclarations(cls, name: str) -> Iterator:
        '''Yields declarations with the given `name` in this class
        and its superclasses.
        '''
        for level in cls.__mro__:
            value = getattr(level, name, None)
            if value is not None:
                yield value

    def __init__(self, attributes: Mapping[str, XMLAttributeValue]):
        self._properties = {
            key: value
            for key, value in attributes.items()
            if value is not None
            }

        # Convert boolean values.
        for decl in self._findDeclarations('boolProperties'):
            for name in cast(Iterable[str], decl):
                value = self._properties.get(name)
                if value in (True, 'True', 'true', 1, '1'):
                    value = True
                elif value in (None, '', False, 'False', 'false', 0, '0'):
                    value = False
                else:
                    raise ValueError(
                        'cannot convert value for "%s" to bool: "%s"'
                        % ( name, value )
                        )
                self._properties[name] = value

        # Convert integer values.
        for decl in self._findDeclarations('intProperties'):
            for name in cast(Iterable[str], decl):
                value = self._properties.get(name)
                if value is not None:
                    self._properties[name] = int(cast(str, value))

        # Convert Enum values.
        for decl in self._findDeclarations('enumProperties'):
            for name, enum in cast(Mapping[str, Type[Enum]], decl).items():
                value = self._properties.get(name)
                if isinstance(value, str):
                    self._properties[name] = enum.__members__[value.upper()]
                elif value is None or isinstance(value, enum):
                    pass
                else:
                    raise TypeError(type(value))

    def __getitem__(self, key: str) -> object:
        return self._properties[key]

    def get(self, key: str, default: object = None) -> object:
        return self._properties.get(key, default)

    def _getContent(self) -> XMLContent:
        '''Returns the XML content for this tag.
        '''
        return ()

    def toXML(self) -> XML:
        return xmlnode(self.tagName)(**self._properties)[self._getContent()]

def parse(factory: object, filenameOrStream: Union[str, IO]) -> object:
    handler = _XMLHandler(factory)
    parser = make_parser()
    parser.setContentHandler(handler)
    parser.setErrorHandler(_errorHandler)
    # We do not use external entities.
    # Disable them as a security precaution.
    parser.setFeature(feature_external_ges, False)
    parser.setFeature(feature_external_pes, False)
    parser.setFeature(feature_string_interning, True)
    parser.setProperty(property_interning_dict, _interningDict)
    parser.parse(filenameOrStream)
    return handler.getParsed()

Host = TypeVar('Host', bound=XMLTag)
Value = TypeVar('Value')
class XMLProperty(Generic[Host, Value]):
    '''Identifies a property in an XMLTag subclass.
    It can be read and written using the "object.member" syntax.
    It cannot be deleted.
    '''

    def __init__(self,
            fget: Optional[Callable[[Host], Value]] = None,
            fset: Optional[Callable[[Host, Value], None]] = None
            ):
        '''Creates a property.
        If no get function is specified, a default one is provided which
        returns the value from the properties dictionary.
        If no set function is specified, the property is read-only.
        '''
        self.__fget = fget
        self.__fset = fset

    def __findMyName(self, objtype: Optional[Type[Host]]) -> str:
        if objtype is None:
            raise AttributeError(
                'cannot find property because type was not specified'
                )
        for name, value in objtype.__dict__.items():
            if value is self:
                return name
        raise AttributeError('property does not belong to this object type')

    def __get__(
            self, obj: Optional[Host], objtype: Optional[Type[Host]] = None
            ) -> Union[Value, 'XMLProperty[Host, Value]']:
        if obj is None:
            # Invoked on class: return XMLProperty object.
            return self
        if self.__fget is None:
            # Create default get function.
            name = self.__findMyName(objtype)
            def fget(obj: Host) -> Value:
                try:
                     # pylint: disable=protected-access
                    return cast(Value, obj._properties[name])
                except KeyError as ex:
                    raise AttributeError(
                        'property "%s" not in dictionary' % name
                        ) from ex
            self.__fget = fget
        # Let get function retrieve the actual value.
        return self.__fget(obj)

    def __set__(self, obj: Host, value: Value) -> None:
        if self.__fset is None:
            raise AttributeError('read-only property')
        self.__fset(obj, value)

    def __delete__(self, obj: Host) -> None:
        raise AttributeError('XML properties cannot be deleted')

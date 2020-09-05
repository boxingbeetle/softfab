# SPDX-License-Identifier: BSD-3-Clause

'''XML generation library: a friendly syntax to create XML in Python.

The syntax is very similar to Nevow's Stan, but the goals and the design are
different:
- Python 2.4 is required
- XML trees are not templates: they are expanded upon initialisation
- more types are accepted as children, including nested sequences,
  and generators
- there are no predefined tag names, so you can define any XML you like,
  not just XHTML
- trailing underscores in attribute names are stripped off, so you can create
  for example a "class" attribute by passing "class_"
TODO: Look again at today's Stan, I think it has changed and there are less
      differences now. The main difference remains though: no templating.

To create an XML tree (data structure consisting of nested XMLNodes):
  from softfab.xmlgen import xml
  xml.<tagname>(<attributes>)[<nested elements>]
where attributes are keyword arguments.
If the tag name contains a minus or is not a constant, you can use the
alternative syntax "xml('tag-name')".
The empty XML tree is represented by None.
The nested elements are one or more elements of the following types:
- other XML trees
- an element from the ElementTree package
- an object that implements "toXML()"; that method should return an XML tree
- an iterable object (list, tuple, generator etc)
  the items from the iterable can be of the same types as the nested elements:
  they are added recursively

Sequences of XML trees are also possible:
- separator.join(trees)
- tree1 + tree2
If you are creating a long sequence, returning an iterable will perform better
than repeated addition.
'''

from collections.abc import Iterable as IterableABC
from enum import Enum
from html.parser import HTMLParser
from itertools import chain
from sys import intern
from types import MappingProxyType, MethodType
from typing import (
    Callable, Dict, Iterable, Iterator, List, Mapping, Match, Optional,
    Sequence, Tuple, Type, Union, cast
)
from xml.etree import ElementTree
from xml.sax.saxutils import escape
import re

from typing_extensions import NoReturn, Protocol

from softfab.utils import cachedProperty


class XMLConvertible(Protocol):
    """Classes can define a `toXML` method to be automatically converted
    to XML when used as XML content.
    """

    def toXML(self) -> 'XMLContent':
        raise NotImplementedError

class XMLPresentable(Protocol):
    """Classes can define a `present` method to generate an XML
    presentation on request. Presentables can be embedded in XML
    content, but an XML tree cannot be flattened until all embedded
    presentations have been resolved.
    """

    def present(self, **kwargs: object) -> 'XMLContent':
        raise NotImplementedError

class XMLSubscriptable(Protocol):
    def __getitem__(self, obj: 'XMLContent') -> 'XML':
        raise NotImplementedError

_reAttributeValueEscapeChars = re.compile('[^ !#$%\'-;=?-~]')
_xmlBuiltinEntities = {
    '\t': '&#x09;',
    '\n': '&#x0A;',
    '\r': '&#x0D;',
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    # Note: &apos; is also a pre-defined entity, but there is no need for us
    #       to escape apostrophes. Even in the case we do want to escape them,
    #       they should be escaped using a numeric escape:
    #         http://www.w3.org/TR/xhtml-media-types/#C_16
    }
def _escapeXMLAttributeChar(match: Match[str]) -> str:
    ch = match.group()
    if ch in _xmlBuiltinEntities:
        return _xmlBuiltinEntities[ch]
    elif ch >= ' ':
        return '&#x%04X;' % ord(ch)
    else:
        raise ValueError('Control character %02X not allowed in XML' % ord(ch))
def _escapeXMLAttributeValue(value: str) -> str:
    '''Converts a given string to an ASCII string that is safe to use as
    an XML attribute value.
    Unlike escape(), this function converts whitespace characters other
    than 0x20 to entities too, to avoid them being normalized by the XML parser.
    See W3C guideline for details:
      http://www.w3.org/TR/xhtml-media-types/#C_5
    '''
    if _reAttributeValueEscapeChars.search(value) is not None:
        value = _reAttributeValueEscapeChars.sub(_escapeXMLAttributeChar, value)
    # Note: XML parsers only collapse whitespace on values declared as NMTOKEN,
    #       not values declared as CDATA. For NMTOKEN values, preservation of
    #       consecutive whitespace characters is neither desired nor feasible
    #       (entity references are not allowed in NMTOKEN values).
    return value

XMLAttributeValue = Union[str, int, Enum, None]
"""Supported types for XML attribute values.
Note that `bool` is a subclass of `int` and therefore also allowed.
"""

class _XMLSerializable:
    '''Base class for objects that can be serialized to XML.
    '''

    def __str__(self) -> str:
        return self.flattenXML()

    def __add__(self, other: 'XMLContent') -> '_XMLSequence':
        return _XMLSequence(chain((self,), _adaptSequence(other)))

    def __radd__(self, other: 'XMLContent') -> '_XMLSequence':
        return _XMLSequence(chain(_adaptSequence(other), (self,)))

    def _toFragments(self, defaultNamespace: Optional[str]) -> Iterator[str]:
        '''Iterates through the fragments forming the XML serialization
        of this object: the XML serialization is the concatenation of
        all the fragments.
        '''
        raise NotImplementedError

    def flattenXML(self) -> str:
        return ''.join(self._toFragments(None))

    def flattenIndented(self) -> str:
        indentedFragments = []
        indent = '\n'
        prevWasElem = False
        for fragment in self._toFragments(None):
            close = fragment.startswith('</')
            open_ = not close and fragment.startswith('<') and \
                    not fragment.startswith('<!')
            if close:
                indent = indent[ : -2]
            if open_ and fragment.endswith('/>'):
                close = True
            thisIsElem = open_ or close
            if prevWasElem and thisIsElem:
                indentedFragments.append(indent)
            indentedFragments.append(fragment)
            if open_ and not close:
                indent += '  '
            prevWasElem = thisIsElem
        indentedFragments.append('\n')
        return ''.join(indentedFragments)

    def present(self, **kwargs: object) -> '_XMLSerializable': # pylint: disable=unused-argument
        '''Returns a presentation of this tree: all presenters will be
        called with the given arguments and replaced in the tree by
        the presentation they return.
        '''
        return self

    def join(self, siblings: Iterable['XMLContent']) -> '_XMLSequence':
        '''Creates an XML sequence with the given siblings as children,
        with itself inserted between each sibling.
        This method is similar to str.join().
        '''
        content: List[_XMLSerializable] = []
        for sibling in siblings:
            content.extend(_adaptSequence(sibling))
            content.append(self)
        if content:
            del content[-1]
        return _XMLSequence(content)

XML = _XMLSerializable

XMLContent = Union[
    str, int, Enum, None,
    XML, ElementTree.Element,
    XMLConvertible, XMLPresentable,
    Iterable
    ]

# For readability, use dedicated prefixes for these namespaces.
_commonAttribNamespaces = {
    'http://www.w3.org/1999/xlink': 'xlink'
    }

def _adaptElementTreeRec(
        element: ElementTree.Element, prefixMap: Dict[str, str]
        ) -> Iterator[XML]:
    text = element.text
    tag = element.tag
    if isinstance(tag, str):
        if tag.startswith('{'):
            index = tag.rindex('}')
            namespace: Optional[str] = tag[1:index]
            tag = tag[index + 1:]
        else:
            namespace = None

        try:
            factory = _nodeFactories[namespace]
        except KeyError:
            factory = _XMLNodeFactory(namespace)

        attrib = element.attrib
        if any(name.startswith('{') for name in attrib):
            attrib = {}
            for name, value in element.attrib.items():
                if name.startswith('{'):
                    index = name.rindex('}')
                    namespace = name[1:index]
                    try:
                        prefix = prefixMap[namespace]
                    except KeyError:
                        prefix = _commonAttribNamespaces.get(
                            namespace, f'ns{len(prefixMap):d}'
                            )
                        prefixMap[namespace] = prefix
                    name = prefix + ':' + name[index + 1:]
                attrib[name] = value

        node = factory(tag)(**attrib)
        if text is not None:
            node = node[_Text(text)]
        yield node[(
            _adaptElementTreeRec(child, prefixMap)
            for child in element
            )]
    elif text is not None:
        yield _Text(text)

    text = element.tail
    if text is not None:
        yield _Text(text)

def _adaptElementTree(element: ElementTree.Element) -> Iterator[XML]:
    # Note: We only use prefixes for attributes.
    prefixMap: Dict[str, str] = {}

    for obj in _adaptElementTreeRec(element, prefixMap):
        if prefixMap and isinstance(obj, XMLNode):
            obj = obj(**{
                'xmlns:' + prefix: namespace
                for namespace, prefix in prefixMap.items()
                })
        yield obj

def _adaptSequence(obj: XMLContent) -> Iterator[XML]:
    if isinstance(obj, _XMLSequence):
        yield from obj._children # pylint: disable=protected-access
    elif isinstance(obj, _XMLSerializable):
        yield obj
    elif isinstance(obj, (str, int)):
        yield _Text(str(obj))
    elif isinstance(obj, Enum):
        yield _Text(obj.name.lower())
    elif obj is None:
        pass
    elif hasattr(obj, 'toXML'):
        yield from _adaptSequence(cast(XMLConvertible, obj).toXML())
    elif hasattr(obj, 'present'):
        yield _PresentationWrapper(cast(XMLPresentable, obj).present)
    elif isinstance(obj, IterableABC):
        if isinstance(obj, bytes):
            # While 'bytes' are iterable, for example b'abc' would be
            # flattened to '979899', which is more likely a bug than
            # intended.
            raise TypeError(type(obj))
        for child in obj:
            yield from _adaptSequence(child)
    elif isinstance(obj, ElementTree.Element):
        yield from _adaptElementTree(obj)
    else:
        raise TypeError(type(obj))

def adaptToXML(obj: XMLContent) -> XML:
    '''Returns an XML tree corresponding to the given object.
    '''
    nodes = tuple(_adaptSequence(obj))
    return nodes[0] if len(nodes) == 1 else _XMLSequence(nodes)

class _PresentationWrapper(_XMLSerializable):

    def __init__(self, func: Callable[..., XMLContent]):
        super().__init__()
        self.__func = func

    def _toFragments(self, defaultNamespace: Optional[str]) -> NoReturn:
        wrapped = self.__func
        if isinstance(wrapped, MethodType):
            if wrapped.__func__.__name__ == 'present':
                wrapped = wrapped.__self__.__class__.__name__
        raise ValueError(f'Unresolved presenter in XML tree: {wrapped}')

    def present(self, **kwargs: object) -> XML:
        return adaptToXML(self.__func(**kwargs))

class _Text(_XMLSerializable):

    def __init__(self, text: str):
        super().__init__()
        self.__text = text

    def _toFragments(self, defaultNamespace: Optional[str]) -> Iterator[str]:
        yield escape(self.__text)

    @property
    def text(self) -> str:
        return self.__text

class _XMLSequence(_XMLSerializable):

    def __init__(self, children: Iterable[XML]):
        '''Creates an XML sequence.
        The given children must all be _XMLSerializable instances;
        if that is not guaranteed, apply _adaptSequence() first.
        '''
        super().__init__()
        self._children: Sequence[XML] = tuple(children)

    def __bool__(self) -> bool:
        return bool(self._children)

    def __len__(self) -> int:
        return len(self._children)

    def __iter__(self) -> Iterator[XML]:
        return iter(self._children)

    def _toFragments(self, defaultNamespace: Optional[str]) -> Iterator[str]:
        for content in self._children:
            # pylint: disable=protected-access
            # "content" is an instance of _XMLSerializable, so we are
            # allowed to access protected methods.
            yield from content._toFragments(defaultNamespace)

    def present(self, **kwargs: object) -> '_XMLSequence':
        changed = False
        children = []
        for child in self._children:
            presentation = child.present(**kwargs)
            if presentation is child:
                children.append(child)
            else:
                children += _adaptSequence(presentation)
                changed = True
        return _XMLSequence(children) if changed else self

_emptySequence = _XMLSequence(())

class XMLNode(_XMLSerializable):
    '''An XML element.
    Do not instantiate this directly; use a node factory like `xml`
    or `xhtml` instead.
    '''

    @classmethod
    def adaptAttributeValue(cls, value: XMLAttributeValue) -> Optional[str]:
        '''Tries to convert the given `value` for an attribute to a string.
        The default implementation handles None and values of the types
        `str`, `int` and `Enum`.
        Returns None if no attribute value should be stored.
        Raises TypeError if `value` is not of a type that can be converted.
        '''
        if isinstance(value, str) or value is None:
            return value
        elif isinstance(value, bool):
            # Note: 'bool' is a subclass of 'int', so test it first.
            return str(value).lower()
        elif isinstance(value, int):
            return str(value)
        elif isinstance(value, Enum):
            return value.name.lower()
        else:
            raise TypeError(type(value))

    def __init__(
            self, namespace: Optional[str], name: str,
            attrs: Mapping[str, str], children: _XMLSequence
            ):
        super().__init__()
        self._namespace = namespace
        self._name = name
        self._attributes = attrs
        self._children = children

    def __call__(self, **attributes: XMLAttributeValue) -> 'XMLNode':
        attrs = dict(self._attributes)
        for key, value in attributes.items():
            key = key.rstrip('_')
            value = self.adaptAttributeValue(value)
            if value is None:
                attrs.pop(key, None)
            else:
                attrs[key] = value
        return self.__class__(
            self._namespace, self._name, attrs, self._children
            )

    def __getitem__(self, index: XMLContent) -> 'XMLNode':
        return self.__class__(
            self._namespace, self._name, self._attributes,
            _XMLSequence(chain(self._children, _adaptSequence(index)))
            )

    def sameTag(self, other: object) -> bool:
        '''Returns True iff `other` is an XML node with the same namespace
        and name as this one; attributes and nested content are ignored.
        '''
        return ( # pylint: disable=protected-access
            isinstance(other, XMLNode) and
            self._namespace is other._namespace and
            self._name == other._name
            )

    @cachedProperty
    def attrs(self) -> Mapping[str, str]:
        return MappingProxyType(self._attributes)

    def addClass(self, name: Optional[str]) -> 'XMLNode':
        '''Appends the given `name` to our `class` attribute.
        This can be used to add a CSS class without overwriting an existing one.
        Returns a new XML node, or this node if `name` was None.
        '''
        if name is None:
            return self

        attrs = dict(self._attributes)
        oldClass = attrs.get('class')
        newClass = name if oldClass is None else f'{oldClass} {name}'
        attrs['class'] = newClass
        return self.__class__(
            self._namespace, self._name, attrs, self._children
            )

    def removeClass(self, name: Optional[str]) -> 'XMLNode':
        '''Removes the given `name` from our `class` attribute.
        This can be used to remove a CSS class without overwriting other
        existing ones.
        Returns a new XML node, or this node if `name` was None or does not
        occur in our `class` attribute.
        '''
        if name is None:
            return self

        try:
            classes = self._attributes['class'].split()
        except KeyError:
            return self
        try:
            classes.remove(name)
        except ValueError:
            return self

        attrs = dict(self._attributes)
        attrs['class'] = ' '.join(classes)
        return self.__class__(
            self._namespace, self._name, attrs, self._children
            )

    def _toFragments(self, defaultNamespace: Optional[str]) -> Iterator[str]:
        namespace = self._namespace
        name = self._name
        attribs = self._attributes

        if namespace is not defaultNamespace and namespace is not None:
            attribs = dict(attribs, xmlns = namespace)
        attribStr = ''.join(
            f' {key}="{_escapeXMLAttributeValue(value)}"'
            for key, value in attribs.items()
            )

        if self._useEmptyTag():
            yield f'<{name}{attribStr}/>'
        else:
            yield f'<{name}{attribStr}>'
            yield from self._contentToFragments()
            yield f'</{name}>'

    def _useEmptyTag(self) -> bool:
        '''Returns True iff this node should be flattened using
        an empty-element tag.
        '''
        return not self._children

    def _contentToFragments(self) -> Iterator[str]:
        # pylint: disable=protected-access
        return self._children._toFragments(self._namespace)

    def present(self, **kwargs: object) -> 'XMLNode':
        children = self._children
        presentation = children.present(**kwargs)
        return self if presentation is children else self.__class__(
            self._namespace, self._name, self._attributes, presentation
            )

class _XHTMLNode(XMLNode):
    '''A node with additional XHTML-specific behavior.
    '''

    @classmethod
    def adaptAttributeValue(cls, value: XMLAttributeValue) -> Optional[str]:
        if isinstance(value, bool):
            # In HTML, Boolean properties are true if present.
            return '' if value else None
        else:
            return super().adaptAttributeValue(value)

    def _useEmptyTag(self) -> bool:
        # Use empty-element tags only for elements that are always empty.
        #   https://dev.w3.org/html5/html-polyglot/#empty-elements
        return False

class _XHTMLVoidNode(_XHTMLNode):
    '''A node that is always empty.
    '''

    def __init__(
            self, namespace: str, name: str,
            attrs: Mapping[str, str], children: _XMLSequence
            ):
        if children:
            raise ValueError(f'Void element <{name}> cannot have children')
        super().__init__(namespace, name, attrs, children)

    def _useEmptyTag(self) -> bool:
        return True

class _XHTMLRawTextNode(_XHTMLNode):
    '''A node that can contain text in which '&' and '<' are not escaped.
    We assume that all script is JavaScript and all style is CSS,
    or languages with the same comment and escape syntax.
    '''

    _reCloseTags = {
        name: re.compile('</' + name, re.I)
        for name in ('script', 'style')
        }
    '''Mapping of tag name to regular expression that matches the close tag.'''

    def __init__(
            self, namespace: str, name: str,
            attrs: Mapping[str, str], children: _XMLSequence
            ):
        for child in children:
            if not isinstance(child, (_Text, _PresentationWrapper)):
                raise ValueError(f'Element <{name}> can only contain text')
        super().__init__(namespace, name, attrs, children)

    def _contentToFragments(self) -> Iterator[str]:
        texts = []
        for child in self._children:
            if isinstance(child, _Text):
                texts.append(child.text)
            elif isinstance(child, _PresentationWrapper):
                raise ValueError(f'Unresolved presenter in <{self._name}>')
            else:
                assert False, child

        if any('<' in text or '&' in text for text in texts):
            # Text has to be placed in a CDATA section.

            # Combine all fragments into a single string, otherwise we might
            # overlook end markers that span multiple fragments.
            text = ''.join(texts)

            # When parsed as XML, ']]>' marks the end of CDATA.
            # JavaScript and CSS parsers will replace '\>' with '>',
            # but XML parsers do not.
            text = text.replace(']]>', ']]\\>')

            # When parsed as HTML, the close tag marks the end.
            # JavaScript and CSS parsers will replace '\/' with '/',
            # but HTML parsers do not.
            text = self._reCloseTags[self._name].sub(
                lambda match: match.group(0).replace('/', '\\/'), text
                )

            yield '/*<![CDATA[*/'
            yield text
            yield '/*]]>*/'
        else:
            # Text can be output as-is.
            yield from texts

_nodeFactories: Dict[Optional[str], '_XMLNodeFactory'] = {}

class _XMLNodeFactory:
    '''Automatically creates XMLNode instances for any tag that is requested:
    if an attribute with a certain name is requested, a new XMLNode with that
    same name is returned.
    '''

    def __init__(self, namespace: Optional[str]):
        super().__init__()
        self._namespace = None if namespace is None else intern(namespace)
        _nodeFactories[namespace] = self

    def __getattr__(self, key: str) -> XMLNode:
        return XMLNode(self._namespace, key, {}, _emptySequence)

    def __call__(self, key: str) -> XMLNode:
        return self.__getattr__(key)

    def __getitem__(self, obj: XMLContent) -> _XMLSequence:
        return _XMLSequence(_adaptSequence(obj))

class _XHTMLNodeFactory(_XMLNodeFactory):

    _voidElements = frozenset((
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'keygen',
        'link', 'meta', 'param', 'source', 'track', 'wbr'
        ))
    '''Names of elements that are always empty and have no end tag.'''

    _rawTextElements = ('script', 'style')
    '''Names of elements that contain unescaped text.'''

    def __getattr__(self, key: str) -> _XHTMLNode:
        if key in self._voidElements:
            nodeClass: Type[_XHTMLNode] = _XHTMLVoidNode
        elif key in self._rawTextElements:
            nodeClass = _XHTMLRawTextNode
        else:
            nodeClass = _XHTMLNode
        return nodeClass(self._namespace, key, {}, _emptySequence)

PI_Handler = Callable[[str], XMLContent]

class _XHTMLParser(HTMLParser):

    def __init__(self,
            piHandlers: Optional[Mapping[str, PI_Handler]] = None
            ) -> None:
        super().__init__()
        self.piHandlers = piHandlers
        self.stack: List[Tuple[XMLNode, List[XMLContent]]] = [
            (cast(XMLNode, None), [])
            ]

    def error(self, message: str) -> NoReturn:
        # This method is not supposed to be called and will be removed
        # in Python 3.8. But until then, PyLint will flag an error if we
        # don't override this abstract method.
        # https://bugs.python.org/issue31844
        assert False

    def handle_starttag(self,
            tag: str,
            attrs: List[Tuple[str, Optional[str]]]
            ) -> None:
        node = xhtml(tag)(**dict(attrs))
        self.stack.append((node, []))

    def handle_endtag(self, tag: str) -> None:
        stack = self.stack
        node, content = stack.pop()
        stack[-1][-1].append(node[content])

    def handle_data(self, data: str) -> None:
        self.stack[-1][-1].append(data)

    def handle_pi(self, data: str) -> None:
        handlers = self.piHandlers
        if handlers is None:
            # User isn't interested in PI.
            return

        # XML processing instructions have a question mark on both ends,
        # while HTML only has one at the start.
        if data.endswith('?'):
            data = data[:-1]

        # Split target from actual data.
        parts = data.split(maxsplit=1)
        if len(parts) == 2:
            target, arg = parts
        else:
            target, = parts
            arg = ''

        # An XML declaration is not a PI, but it looks like one to
        # an HTML parser.
        if target == 'xml':
            return

        # Call the registered handler for the target.
        handler = handlers[target]
        result = handler(arg.strip())
        self.stack[-1][-1].append(result)

def parseHTML(
        html: str, *,
        piHandlers: Optional[Mapping[str, PI_Handler]] = None
        ) -> XML:
    """Parses an HTML document or fragment.

    If nothing is passed for `piHandlers`, processing instructions (PI)
    will be silently ignored.
    If a mapping is passed, the PI's target will be used as a key to look
    up a PI handler function which will be called with the PI's data.
    The XML content returned by the handler is inserted at the point in
    the document where the PI was.
    KeyError will be raised if there is a PI handler mapping but the PI's
    target isn't in the mapping.
    """
    parser = _XHTMLParser(piHandlers)
    parser.feed(html)
    (_, content), = parser.stack
    return xhtml[content]

xml = _XMLNodeFactory(None)
atom = _XMLNodeFactory('http://www.w3.org/2005/Atom')
xhtml = _XHTMLNodeFactory('http://www.w3.org/1999/xhtml')

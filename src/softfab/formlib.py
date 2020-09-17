# SPDX-License-Identifier: BSD-3-Clause

from collections.abc import Collection as CollectionABC
from enum import Enum
from typing import (
    TYPE_CHECKING, Any, ClassVar, Collection, Iterable, Iterator, List,
    Mapping, Optional, Sequence, Set, Tuple, Type, Union, cast
)

from typing_extensions import NoReturn

from softfab.pageargs import PageArgs, dynamic, mandatory
from softfab.utils import abstract, iterable
from softfab.webgui import (
    AttrContainer, Column, Table, Widget, cell, row, script
)
from softfab.xmlgen import (
    XML, XMLAttributeValue, XMLContent, XMLNode, XMLPresentable, xhtml
)

if TYPE_CHECKING:
    from softfab.Page import PageProcessor
else:
    PageProcessor = object


class _FormPresenter:
    '''Utility class to create forms in HTML pages.
    It provides methods that generate the HTML code for you.
    In addition, it keeps track of all controls in a form, so it can
    automatically generate JavaScript code for features such as auto-focus
    and clear button.

    TODO: Not every control type calls addClearCode() yet.
    '''

    def __init__(self, formId: Optional[str], autoFocus: bool):
        # TODO: If formId is None, what to do:
        #       - disallow use of methods that require ID?
        #         (is it clear to the user which ones require ID?)
        #       - auto-generate ID?
        #         (how do we guarantee uniqueness?)
        super().__init__()
        self.__id = formId
        self.__autoFocus = autoFocus
        self.__controls: Set[str] = set()
        self.__clearCode: List[str] = []
        self.hasClearButton = False

    @property
    def id(self) -> str:
        formId = self.__id
        assert formId is not None
        return formId

    def addControl(self, name: Optional[str], focus: bool) -> bool:
        if name is not None:
            self.__controls.add(name)

        if focus:
            focus = self.__autoFocus
            if focus:
                self.__autoFocus = False
        return focus

    def addClearCode(self, *lines: str) -> None:
        self.__clearCode += lines

    def __iterScriptFragments(self) -> Iterator[str]:
        if self.hasClearButton:
            yield 'function clearForm() {'
            yield f'\tinputs = document.forms.{self.__id}.elements;'
            for line in self.__clearCode:
                yield '\t' + line
            yield '}'

    def iterCloseItems(self, args: Optional[PageArgs]) -> XMLContent:
        if args is not None:
            controls = self.__controls
            for key, values in args.externalize():
                if key not in controls:
                    for value in values:
                        yield xhtml.input(type='hidden', name=key, value=value)
        yield script[ self.__iterScriptFragments() ].present()

class _FormBuilder(AttrContainer, XMLPresentable):

    def __init__(self,
                 formArgs: Tuple[Optional[str], Optional[PageArgs], bool],
                 contents: Iterable[XMLPresentable],
                 attributes: Mapping[str, object]):
        super().__init__(contents, attributes)
        self.__formArgs = formArgs

    def _replaceContents(self, contents: Iterable[XMLPresentable]
                         ) -> '_FormBuilder':
        return self.__class__(self.__formArgs, contents, self._attributes)

    def _replaceAttributes(self,
                           attributes: Mapping[str, object]
                           ) -> '_FormBuilder':
        return self.__class__(self.__formArgs, self._contents, attributes)

    def present(self, **kwargs: object) -> XML:
        # HTML does not support nested forms, so there is no point in
        # supporting them here.
        assert 'form' not in kwargs, kwargs['form']

        proc = cast(PageProcessor, kwargs['proc'])

        formId, args, setFocus = self.__formArgs
        form = _FormPresenter(formId, setFocus)
        if args is None:
            args = proc.args

        # Force all content presenters to run and register their
        # controls with the form.
        content = tuple(self._presentContents(
            form=form, formArgs=args, **kwargs
            ))

        # TODO: Should attribute type become a type argument of AttrContainer
        #       or is casting like this a good enough solution?
        attributes = dict(cast(
            Mapping[str, XMLAttributeValue],
            self._attributes
            ))
        assert 'id' not in attributes, attributes['id']
        attributes['id'] = formId
        attributes.setdefault('action', proc.page.name)
        return xhtml.form(**attributes)[
            content,
            form.iterCloseItems(args)
            ]

def makeForm(formId: Optional[str] = None,
             args: Optional[PageArgs] = None,
             setFocus: bool = True,
             **attributes: XMLAttributeValue
             ) -> _FormBuilder:
    '''Defines an HTML form.
    Content can be added to it using [], similar to how xmlgen works.
    If no action is provided, the form will be submitted to the page
    that contains it.
    '''
    attributes.setdefault('method', 'post')
    return _FormBuilder((formId, args, setFocus), (), attributes)

def _argValue(args: Optional[PageArgs], name: str) -> object:
    """Return the value for the page argument `name`,
    or None if no match could be found in `args`.
    """
    if args is None:
        return None
    try:
        return args.valueForWidget(name)
    except KeyError:
        return None

def _argDefault(args: Optional[PageArgs], name: str) -> object:
    """Return the default value for the page argument `name`,
    or None if no default could be determined.
    """
    if args is None:
        return None
    try:
        return args.defaultForWidget(name)
    except KeyError:
        return None

class _SubmitButton(AttrContainer, XMLPresentable):

    def present(self, **kwargs: object) -> XMLContent:
        form = cast(_FormPresenter, kwargs['form'])
        attributes = self._attributes

        name = cast(Optional[str], attributes.get('name'))
        focus = form.addControl(name, True)

        value = cast(Optional[str], attributes.get('value'))
        if value is None:
            value = 'submit'
            attributes = dict(attributes, value = value)

        label: XMLContent = tuple(self._presentContents(**kwargs))
        if not label:
            # Automatically create label.
            words: Sequence[str]
            if isinstance(value, Enum):
                words = (value.name.lower(), )
            else:
                words = value.split('_')
            label = ' '.join(word.capitalize() for word in words)

        button = xhtml.button(autofocus=focus, **attributes)[ label ]
        if button.attrs['value'] == 'cancel':
            return button(formnovalidate=True)
        else:
            return button

submitButton = _SubmitButton((), dict(tabindex = 1, type = 'submit'))

class _ResetButton(AttrContainer, XMLPresentable):

    def present(self, **kwargs: object) -> XMLContent:
        label: XMLContent = tuple(self._presentContents(**kwargs))
        if not label:
            label = 'Revert'

        return xhtml.button(**self._attributes)[ label ]

resetButton = _ResetButton((), dict(tabindex = 1, type = 'reset'))

class _ClearButton(AttrContainer, XMLPresentable):

    def present(self, **kwargs: object) -> XMLContent:
        form = cast(_FormPresenter, kwargs['form'])
        form.hasClearButton = True

        label: XMLContent = tuple(self._presentContents(**kwargs))
        if not label:
            label = 'Clear'

        return xhtml.button(**self._attributes)[ label ]

clearButton = _ClearButton(
    (), dict(tabindex = 1, type = 'button', onclick = 'clearForm()')
    )
'''A button that, when pressed, will clear the form it is part of.
While "Revert" resets the fields to the state of the form as it was
delivered by the Control Center, "Clear" resets the fields to an empty
state.
'''

class _BackButton(AttrContainer, XMLPresentable):

    def present(self, **kwargs: object) -> XMLContent:
        form = cast(_FormPresenter, kwargs['form'])
        attributes = self._attributes

        name = cast(Optional[str], attributes.get('name'))
        # Note: Add the back button as no-focus control instead of
        #       visible control, since the latter would give the
        #       top back button focus in Dialog-based pages.
        form.addControl(name, False)

        if name is None:
            attributes = dict(attributes, disabled = True)

        label: XMLContent = tuple(self._presentContents(**kwargs))
        if not label:
            label = '< Back'

        return xhtml.button(**attributes)[ label ]

backButton = _BackButton(
    (), dict(tabindex=2, formnovalidate=True, type='submit', value='back')
    )

disabledButton = xhtml.button(
    type = 'button', tabindex = 1, disabled = True
    )

def actionButtons(*values: Union[XMLAttributeValue, Type[Enum]],
                  name: str = 'action',
                  **kwargs: XMLAttributeValue
                  ) -> XML:
    '''Creates a series of buttons with the given submission values and
    labels derived from those values.
    Returns an XML node containing the button widgets, separated by spaces.
    The keyword arguments are used as HTML attributes on each button.
    The value arguments can either be string and Enums.
    '''
    valueStrings = []
    for value in values:
        if isinstance(value, str):
            valueStrings.append(value)
        elif isinstance(value, Enum):
            valueStrings.append(value.name)
        elif isinstance(value, type) and issubclass(value, Enum):
            valueStrings += value.__members__
        else:
            raise TypeError(type(value))

    return xhtml[' '].join(
        submitButton(name = name, value = value, **kwargs)
        for value in valueStrings
        )

class _HiddenInput(AttrContainer, XMLPresentable):

    def _replaceContents(self, contents: Iterable[XMLPresentable]) -> NoReturn:
        raise ValueError(
            '"hiddenInput" does not support nested content; '
            'use the "value" attribute instead'
            )

    def present(self, **kwargs: object) -> XMLContent:
        form = cast(_FormPresenter, kwargs['form'])
        attributes = self._attributes

        name = cast(Optional[str], attributes.get('name'))
        if name is None:
            return None
        form.addControl(name, False)

        if 'value' in attributes:
            return xhtml.input(**attributes)
        else:
            return None

hiddenInput = _HiddenInput((), dict(type = 'hidden'))

class _TextInput(AttrContainer, XMLPresentable):

    def _replaceContents(self, contents: Iterable[XMLPresentable]) -> NoReturn:
        raise ValueError(
            '"textInput" does not support nested content; '
            'use the "value" attribute instead'
            )

    def present(self, **kwargs: Any) -> XMLContent:
        form: _FormPresenter = kwargs['form']
        attributes = self._attributes

        if 'autofocus' in attributes:
            attributes = dict(attributes)
            wantFocus = attributes.pop('autofocus')
            if not isinstance(wantFocus, bool):
                raise TypeError(type(wantFocus))
        else:
            wantFocus = True
        if attributes.get('disabled', False):
            wantFocus = False

        name = cast(Optional[str], attributes.get('name'))
        focus = form.addControl(name, wantFocus)

        if name is not None:
            form.addClearCode(f'inputs.{name}.value = "";')

            if 'value' not in attributes:
                value = _argValue(kwargs['formArgs'], name)
                if isinstance(value, (Enum, str, int)):
                    attributes = dict(attributes, value = value)
                elif value is not None:
                    raise TypeError(type(value))

        return xhtml.input(autofocus=focus, **attributes)

textInput = _TextInput((), dict(type = 'text', tabindex = 1))
passwordInput = _TextInput((), dict(type = 'password', tabindex = 1))

class _TextArea(AttrContainer, XMLPresentable):

    def present(self, **kwargs: object) -> XMLContent:
        form = cast(_FormPresenter, kwargs['form'])
        attributes = self._attributes

        name = cast(Optional[str], attributes.get('name'))
        focus = form.addControl(name, True)

        contents: XMLContent = tuple(self._presentContents(**kwargs))
        if not contents and name is not None:
            formArgs = cast(PageArgs, kwargs['formArgs'])
            value = _argValue(formArgs, name)
            if isinstance(value, str):
                contents = value
            elif value is not None:
                raise TypeError(type(value))

        return xhtml.textarea(autofocus=focus, **attributes)[contents]

textArea = _TextArea((), dict(tabindex = 1))

option = xhtml.option
emptyOption = option(value = '')

class _Select(AttrContainer, XMLPresentable):

    def _adaptContentElement(self, element: XMLContent
                             ) -> Iterator[XMLPresentable]:
        if option.sameTag(element):
            yield cast(XML, element)
        elif isinstance(element, (str, int, Enum)):
            yield option(value = element)[ element ]
        elif iterable(element):
            for child in cast(Iterable[XMLContent], element):
                yield from self._adaptContentElement(child)
        elif isinstance(element, type) and issubclass(element, Enum):
            for value in element.__members__.values():
                yield option(value = value)[ value ]
        elif hasattr(element, 'present'):
            yield cast(XMLPresentable, element)
        else:
            raise TypeError(
                f'Cannot adapt "{type(element).__name__}" to selection option'
                )

    def present(self, **kwargs: Any) -> XMLContent:
        form: _FormPresenter = kwargs['form']
        formArgs: Optional[PageArgs] = kwargs['formArgs']
        attributes = self._attributes

        multiple = attributes.get('multiple', False)

        name = cast(Optional[str], attributes.get('name'))
        focus = form.addControl(name, not attributes.get('disabled', False))

        if name is not None:
            if multiple:
                form.addClearCode(
                    f'var options = inputs.{name}.options;',
                    'for (var i = 0; i < options.length; i++) {',
                    '\toptions[i].selected = false;',
                    '}'
                    )
            else:
                default = _argDefault(formArgs, name)
                if default not in (None, dynamic, mandatory):
                    if iterable(default):
                        # Multiple drop-down lists are combined to populate
                        # a single argument.
                        value: Optional[str] = ''
                    else:
                        value = option.adaptAttributeValue(cast(str, default))
                    form.addClearCode(
                        f'inputs.{name}.value = "{value}";'
                        )

        if 'selected' in attributes:
            attributes = dict(attributes)
            selected = attributes.pop('selected')
        elif name is None:
            selected = None
        else:
            selected = _argValue(formArgs, name)

        selectedSet = set()
        if selected is not None:
            if multiple:
                if not iterable(selected):
                    raise TypeError(
                        f'singular ({type(selected).__name__}) '
                        f'"selected" attribute for multi-select'
                        )
            else:
                selected = (selected, )
            for item in cast(Iterable[XMLAttributeValue], selected):
                itemStr = option.adaptAttributeValue(item)
                if itemStr is not None:
                    selectedSet.add(itemStr)

        optionsPresentation = []
        for content in self._presentContents(**kwargs):
            if option.sameTag(content):
                node = cast(XMLNode, content)
                if node.attrs.get('value') in selectedSet:
                    node = node(selected = True)
                optionsPresentation.append(node)
            else:
                raise ValueError(f'Expected <option>, got {content}')

        return xhtml.select(autofocus=focus, **attributes)[
            optionsPresentation
            ]

dropDownList = _Select((), dict(tabindex = 1))
'''A drop-down list from which a single item can be selected.
Contents must be <option> elements or values from which <option> elements
can be created: single string/integer/Enum values, Enum types or widgets.
In addition to the HTML attributes of the <select> element, the widget
accepts a `selected` argument to pick the selected option. If this
argument is not provided, the selected option is determined by the value
of the form argument that matches the widget's name.
'''

selectionList = _Select((), dict(tabindex = 1, multiple = True))
'''A list from which multiple items can be selected.
Contents must be <option> elements or values from which <option> elements
can be created: single string/integer/Enum values, Enum types or widgets.
In addition to the HTML attributes of the <select> element, the widget
accepts a `selected` argument to pick the selected options. If this
argument is not provided, the selected options are determined by the value
of the form argument that matches the widget's name.
'''

Option = Union[
    str,
    Tuple[XMLContent, str],
    Tuple[str, Iterable[Union[str, Tuple[XMLContent, str]]]]
    ]

class DropDownList(Widget):
    name: ClassVar[str] = abstract
    extraAttribs: Optional[Mapping[str, str]] = None

    def present(self, **kwargs: object) -> XMLContent:
        form = cast(_FormPresenter, kwargs['form'])

        # Drop-down lists without a name cannot be submitted, but can be
        # useful with JavaScript.
        name = self.name
        focus = form.addControl(name, True)
        if name is not None:
            default = self.getDefault(**kwargs)
            if default is not None and default is not mandatory:
                value = option.adaptAttributeValue(
                                    cast(XMLAttributeValue, default))
                form.addClearCode(f'inputs.{name}.value = "{value}";')

        extraAttribs = self.extraAttribs or {}
        return xhtml.select(
            tabindex=1, name=self.name, autofocus=focus, **extraAttribs
            )[
            _presentOptions(
                self.iterOptions(**kwargs),
                self.getActive(**kwargs)
                )
            ]

    def getActive(self, **kwargs: object) -> Optional[str]:
        '''Returns the active option, or None if no option is active.
        '''
        raise NotImplementedError

    def getDefault(self, **kwargs: Any) -> object:
        '''Returns the default option, or None so skip the generation of
        the form clear code.
        The default implementation returns the default value of the form
        argument with the same name as this widget, or None if no default
        could be determined.
        '''
        return _argDefault(kwargs['formArgs'], self.name)

    def iterOptions(self, **kwargs: object) -> Iterator[Option]:
        '''Iterates through the multiple choice options.
        Elements can be a string, which is used for both the value and the
        label of the option, a pair of a label and a value string, or a
        pair of a label and sequence of options, which is presented as an
        options group.
        Option groups can in turn contain nested option groups; this is
        not expressed in the type annotation because mypy doesn't support
        recursive types yet.
        '''
        raise NotImplementedError

def _presentOptions(options: Iterable[Option],
                    selected: Optional[str],
                    prefix:  Optional[str] = None
                    ) -> Iterator[XML]:
    '''Generate XHTML for the given options, which can contain nested options.
    Note: This used to be an internal function of DropDownList.present(), but
          recursive inner functions are not collected by the refcounting
          garbage collection, which means a memory leak since we have
          the mark-and-sweep collector turned off.
    '''
    empty = True
    for item in options:
        empty = False
        label: XMLContent
        value: Union[str, Iterable[Option]]
        if isinstance(item, str):
            label = value = item
        else:
            label, value = item
        if isinstance(value, str):
            if prefix is not None:
                value = prefix + value
            yield xhtml.option(
                value = value,
                selected = value == selected
                )[ label ]
        else:
            assert isinstance(label, str), label
            yield xhtml.optgroup(label=label)[
                _presentOptions(value, selected, label + ',')
                ]
    if empty:
        # Empty <select> or <optgroup> is not allowed by the DTD.
        yield xhtml.option(disabled = True)[ '(list is empty)' ]

class _CheckBox(AttrContainer, XMLPresentable):

    def present(self, **kwargs: Any) -> XMLContent:
        form: Optional[_FormPresenter] = kwargs.get('form')
        attributes = self._attributes

        name = cast(Optional[str], attributes.get('name'))
        if form is None:
            focus = False
        else:
            focus = form.addControl(name, True)

        if 'checked' not in attributes and name is not None:
            value = _argValue(kwargs['formArgs'], name)
            if isinstance(value, bool):
                checked = value
            elif isinstance(value, frozenset):
                checked = attributes['value'] in value
            else:
                raise TypeError(type(value))
            if checked:
                attributes = dict(attributes, checked=True)

        box = xhtml.input(type='checkbox', autofocus=focus, **attributes)
        label = tuple(self._presentContents(**kwargs))
        return xhtml.label[ box, label ] if label else box

checkBox = _CheckBox((), dict(value='true', tabindex=1))

class CheckBoxesTable(Table):
    name: ClassVar[str] = abstract

    def present(self, **kwargs: object) -> XMLContent:
        yield super().present(**kwargs)
        # TODO: If there are multiple CheckBoxesTable widgets on
        #       the same page, we now duplicate the script.
        yield _toggleRowScript.present(**kwargs)

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        form = cast(_FormPresenter, kwargs['form'])
        active = self.getActive(**kwargs)
        first = True
        for key, cells in self.iterOptions(**kwargs):
            if first:
                focus = form.addControl(self.name, True)
                first = False
            else:
                focus = False
            boxCell: XMLContent = cell(class_='clickable',
                                       onclick='toggleRow(event)')[
                xhtml.label[
                    xhtml.input(
                        type = 'checkbox', tabindex = 1,
                        name = self.name, value = key,
                        checked = key in active, autofocus = focus
                        ), ' ', cells[0]
                    ]
                ]
            yield (boxCell,) + tuple(cells[1 : ])

    def getActive(self, **kwargs: Any) -> Collection[object]:
        '''Returns the active options.
        The default implementation returns the value of the argument that
        matches the submission name of this check boxes table.
        '''
        active = _argValue(kwargs['formArgs'], self.name)
        if isinstance(active, CollectionABC):
            return active
        else:
            raise TypeError(type(active))

    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[str, Sequence[XMLContent]]]:
        '''Iterates through the multiple choice options.
        Each element should be a tuple where the first position contains
        the key belonging to that option and the other positions are
        cell contents.
        '''
        raise NotImplementedError

class SingleCheckBoxTable(CheckBoxesTable):
    '''Special check boxes table which offers only a single check box.
    '''
    name: ClassVar[str] = abstract
    columns = None,
    label: ClassVar[str] = abstract
    '''Label for the check box.'''

    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[str, Sequence[XMLContent]]]:
        yield 'true', ( self.label, )

    def isActive(self, **kwargs: Any) -> bool:
        '''Returns True iff the single check box is active.
        The default implementation returns the value of the argument that
        matches the submission name of this check boxes table.
        '''
        active = _argValue(kwargs['formArgs'], self.name)
        if not isinstance(active, bool):
            raise TypeError(
                f'Invalid page argument value type: expected "bool", '
                f'got "{type(active).__name__}"'
                )
        return active

    def getActive(self, **kwargs: object) -> Collection[str]:
        if self.isActive(**kwargs):
            return 'true',
        else:
            return ()

_toggleRowScript = script[
r'''
function toggleRow(event) {
    var target = event.target;
    var node = target;
    while (node.tagName != "tr") node = node.parentNode;
    var inputs = node.getElementsByTagName("input");
    if (target.tagName == "td") {
        inputs[0].checked ^= true;
    }
    for (i = 1; i < inputs.length; i++) {
        inputs[i].disabled = !inputs[0].checked;
    }
}
''']

class RadioTable(Table):
    name = cast(str, None)
    '''Name is mandatory, but sometimes static and sometimes computed.'''

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        form = cast(_FormPresenter, kwargs['form'])
        formId = form.id
        name = self.name
        active = self.getActive(**kwargs)
        for index, item in enumerate(self.iterOptions(**kwargs)):
            focus = index == 0 and form.addControl(name, True)
            key = cast(str, item[0])
            box = xhtml.input(
                type = 'radio', tabindex = 1, name = name, value = key,
                checked = key == active, autofocus = focus
                )
            yield row(
                # Note: While clicking the label will activate the button,
                #       the JavaScript reacts to the entire row.
                onclick=f"document.forms.{formId}['{name}'][{index:d}]"
                                                            '.checked=true',
                class_='clickable'
                )[ self.formatOption(box, item[1:]) ]

    def getActive(self, **kwargs: Any) -> Union[None, str, Enum]:
        '''Returns the active option, or None if no option is active.
        The default implementation returns the value of the page argument
        with the same name as this control.
        '''
        active = _argValue(kwargs['formArgs'], self.name)
        if active is None or isinstance(active, (str, Enum)):
            return active
        else:
            raise TypeError(type(active))

    def iterOptions(self, **kwargs: object) -> Iterator[Sequence[XMLContent]]:
        '''Iterates through the multiple choice options.
        Each element should be a tuple where the first position contains
        the key belonging to that option and the other positions are
        cell contents.
        TODO: CheckBoxesTable puts the cells in a nested sequence instead.
              It would be good to be consistent and CheckBoxesTable's
              interface offers more type safety.
        '''
        raise NotImplementedError

    def formatOption(self,
                     box: XML,
                     cells: Sequence[XMLContent]
                     ) -> XMLContent:
        '''Formats the given `box` and `cells` into row contents.
        The default implementation puts the radio box into the first column
        with the entire first cell as its label and puts the other cells in
        the remaining columns.
        Each label can contain only one input element, so if your first column
        contains an input other than the radio box, you have to override this
        method.
        '''
        boxCell: XMLContent = xhtml.label[box, ' ', cells[0]]
        return (boxCell,) + tuple(cells[1:])

class FormTable(Table):
    '''Presents a form as a table, where each row contains a form field.
    '''
    labelStyle: Optional[str] = None
    '''CSS class for field label cells.'''
    fieldStyle: Optional[str] = None
    '''CSS class for field widget cells.'''
    style = 'properties'

    def iterColumns(self, **kwargs: object) -> Iterator[Column]:
        yield Column(None, cellStyle = self.labelStyle)
        yield Column(None, cellStyle = self.fieldStyle)

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        for label, widget in self.iterFields(**kwargs):
            yield label + ':', widget

    def iterFields(self, **kwargs: object) -> Iterator[Tuple[str, XMLContent]]:
        '''Iterates through the fields in this form.
        Each element should be a (label, widget) pair.
        '''
        raise NotImplementedError

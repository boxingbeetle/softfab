# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import ClassVar, Mapping, Optional

from softfab.pageargs import dynamic, mandatory
from softfab.utils import abstract, iterable
from softfab.webgui import (
    AttrContainer, Column, Table, Widget, cell, row, script
    )
from softfab.xmlgen import XMLPresentable, txt, xhtml

class _FormPresenter:
    '''Utility class to create forms in HTML pages.
    It provides methods that generate the HTML code for you.
    In addition, it keeps track of all controls in a form, so it can
    automatically generate JavaScript code for features such as auto-focus
    and clear button.

    TODO: Not every control type calls addClearCode() yet.
    '''

    def __init__(self, formId, autoFocus):
        # TODO: If formId is None, what to do:
        #       - disallow use of methods that require ID?
        #         (is it clear to the user which ones require ID?)
        #       - auto-generate ID?
        #         (how do we guarantee uniqueness?)
        self.__id = formId
        self.__autoFocus = autoFocus
        self.__controls = set()
        self.__clearCode = []
        self.hasClearButton = False

    @property
    def id(self):
        formId = self.__id
        assert formId is not None
        return formId

    def addControl(self, name, focus):
        if name is not None:
            self.__controls.add(name)

        if focus:
            focus = self.__autoFocus
            if focus:
                self.__autoFocus = False
        return focus

    def addClearCode(self, *lines):
        self.__clearCode += lines

    def __iterScriptFragments(self):
        if self.hasClearButton:
            yield 'function clearForm() {'
            yield '\tinputs = document.forms.%s.elements;' % self.__id
            for line in self.__clearCode:
                yield '\t' + line
            yield '}'

    def iterCloseItems(self, args):
        if args is not None:
            controls = self.__controls
            for key, value in args.toQuery():
                if key not in controls and value is not None:
                    yield xhtml.input(type='hidden', name=key, value=value)
        yield script[ self.__iterScriptFragments() ].present()

class _FormBuilder(AttrContainer, XMLPresentable):

    def __init__(self, formArgs, contents, attributes):
        super().__init__(contents, attributes)
        self.__formArgs = formArgs

    def _replaceContents(self, contents):
        return self.__class__(self.__formArgs, contents, self._attributes)

    def _replaceAttributes(self, attributes):
        return self.__class__(self.__formArgs, self._contents, attributes)

    def present(self, *, proc, form=None, **kwargs):
        # HTML does not support nested forms, so there is no point in
        # supporting them here.
        assert form is None, form

        formId, args, setFocus = self.__formArgs
        form = _FormPresenter(formId, setFocus)
        if args is None:
            args = proc.args

        # Force all content presenters to run and register their
        # controls with the form.
        content = tuple(self._presentContents(
            proc=proc, form=form, formArgs=args, **kwargs
            ))

        attributes = dict(self._attributes)
        assert 'id' not in attributes, attributes['id']
        attributes['id'] = formId
        attributes.setdefault('action', proc.page.name)
        return xhtml.form(**attributes)[
            content,
            form.iterCloseItems(args)
            ]

def makeForm(formId = None, args = None, setFocus = True, **attributes):
    '''Defines an HTML form.
    Content can be added to it using [], similar to how xmlgen works.
    If no action is provided, the form will be submitted to the page
    that contains it.
    '''
    attributes.setdefault('method', 'post')
    return _FormBuilder((formId, args, setFocus), (), attributes)

def _getDefault(args, name):
    '''Returns the default value for the argument with the given `name`,
    or None if no default could be determined.
    '''
    if args is None:
        return None
    argDecl = getattr(args.__class__, name, None)
    if argDecl is None or not args.isArgument(name):
        return None
    else:
        return argDecl.default

class _SubmitButton(AttrContainer, XMLPresentable):

    def present(self, *, form, **kwargs):
        attributes = self._attributes

        name = attributes.get('name')
        focus = form.addControl(name, True)

        value = attributes.get('value')
        if value is None:
            value = 'submit'
            attributes = dict(attributes, value = value)

        label = tuple(self._presentContents(form=form, **kwargs))
        if not label:
            # Automatically create label.
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

    def present(self, **kwargs):
        label = tuple(self._presentContents(**kwargs))
        if not label:
            label = 'Revert'

        return xhtml.button(**self._attributes)[ label ]

resetButton = _ResetButton((), dict(tabindex = 1, type = 'reset'))

class _ClearButton(AttrContainer, XMLPresentable):

    def present(self, *, form, **kwargs):
        form.hasClearButton = True

        label = tuple(self._presentContents(form=form, **kwargs))
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

    def present(self, *, form, **kwargs):
        attributes = self._attributes

        name = attributes.get('name')
        # Note: Add the back button as no-focus control instead of
        #       visible control, since the latter would give the
        #       top back button focus in Dialog-based pages.
        form.addControl(name, False)

        if name is None:
            attributes = dict(attributes, disabled = True)

        label = tuple(self._presentContents(form=form, **kwargs))
        if not label:
            label = '< Back'

        return xhtml.button(**attributes)[ label ]

backButton = _BackButton(
    (), dict(tabindex=2, formnovalidate=True, type='submit', value='back')
    )

disabledButton = xhtml.button(
    type = 'button', tabindex = 1, disabled = True
    )

def actionButtons(*values, name = 'action', **kwargs):
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

    return txt(' ').join(
        submitButton(name = name, value = value, **kwargs)
        for value in valueStrings
        )

class _HiddenInput(AttrContainer, XMLPresentable):

    def _replaceContents(self, contents):
        raise ValueError(
            '"hiddenInput" does not support nested content; '
            'use the "value" attribute instead'
            )

    def present(self, *, form, **kwargs):
        attributes = self._attributes

        name = attributes.get('name')
        if name is None:
            return None
        form.addControl(name, False)

        if 'value' in attributes:
            return xhtml.input(**attributes)
        else:
            return None

hiddenInput = _HiddenInput((), dict(type = 'hidden'))

class _TextInput(AttrContainer, XMLPresentable):

    def _replaceContents(self, contents):
        raise ValueError(
            '"textInput" does not support nested content; '
            'use the "value" attribute instead'
            )

    def present(self, *, form, formArgs, **kwargs):
        attributes = self._attributes

        name = attributes.get('name')
        focus = form.addControl(name, not attributes.get('disabled', False))

        if name is not None:
            form.addClearCode('inputs.%s.value = "";' % name)

            if 'value' not in attributes:
                if formArgs is not None:
                    value = getattr(formArgs, name, None)
                    if isinstance(value, (Enum, str, int)):
                        attributes = dict(attributes, value = value)
                    elif value is not None:
                        raise TypeError(type(value))

        return xhtml.input(autofocus=focus, **attributes)

textInput = _TextInput((), dict(type = 'text', tabindex = 1))
passwordInput = _TextInput((), dict(type = 'password', tabindex = 1))

class _TextArea(AttrContainer, XMLPresentable):

    def present(self, *, form, formArgs, **kwargs):
        attributes = self._attributes
        name = attributes.get('name')
        focus = form.addControl(name, True)

        contents = tuple(self._presentContents(
            form=form, formArgs=formArgs, **kwargs
            ))
        if not contents and name is not None:
            if formArgs is not None:
                value = getattr(formArgs, name, None)
                if isinstance(value, str):
                    contents = txt(value)
                elif value is not None:
                    raise TypeError(type(value))

        return xhtml.textarea(autofocus=focus, **attributes)[contents]

textArea = _TextArea((), dict(tabindex = 1))

option = xhtml.option
emptyOption = option(value = '')

class _Select(AttrContainer, XMLPresentable):

    def _adaptContentElement(self, element):
        if option.sameTag(element):
            yield element
        elif isinstance(element, (str, int, Enum)):
            yield option(value = element)[ element ]
        elif iterable(element):
            for child in element:
                yield from self._adaptContentElement(child)
        elif isinstance(element, type) and issubclass(element, Enum):
            for value in element.__members__.values():
                yield option(value = value)[ value ]
        elif isinstance(element, XMLPresentable):
            yield element
        else:
            raise TypeError(
                'Cannot adapt "%s" to selection option' % type(element).__name__
                )

    def present(self, *, form, formArgs, **kwargs):
        attributes = self._attributes

        multiple = attributes.get('multiple', False)

        name = attributes.get('name')
        focus = form.addControl(name, not attributes.get('disabled', False))

        if name is not None:
            if multiple:
                form.addClearCode(
                    'var options = inputs.%s.options;' % name,
                    'for (var i = 0; i < options.length; i++) {',
                    '\toptions[i].selected = false;',
                    '}'
                    )
            else:
                default = _getDefault(formArgs, name)
                if default not in (None, dynamic, mandatory):
                    if iterable(default):
                        # Multiple drop-down lists are combined to populate
                        # a single argument.
                        value = ''
                    else:
                        value = option.adaptAttributeValue(default)
                    form.addClearCode(
                        'inputs.%s.value = "%s";' % (name, value)
                        )

        if 'selected' in attributes:
            attributes = dict(attributes)
            selected = attributes.pop('selected')
        elif name is None:
            selected = None
        else:
            selected = getattr(formArgs, name, None)

        selectedSet = set()
        if selected is not None:
            if multiple:
                if not iterable(selected):
                    raise TypeError(
                        'singular (%s) "selected" attribute for multi-select'
                        % type(selected)
                        )
            else:
                selected = (selected, )
            for item in selected:
                itemStr = option.adaptAttributeValue(item)
                if itemStr is not None:
                    selectedSet.add(itemStr)

        optionsPresentation = []
        for content in self._presentContents(
                form=form, formArgs=formArgs, **kwargs
                ):
            if option.sameTag(content):
                if content.attrs.get('value') in selectedSet:
                    content = content(selected = True)
                optionsPresentation.append(content)
            else:
                raise ValueError('Expected <option>, got %s' % content)

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

class DropDownList(Widget):
    name = abstract # type: ClassVar[str]
    extraAttribs = None # type: Optional[Mapping[str, str]]

    def present(self, *, form, formArgs, **kwargs):
        # Drop-down lists without a name cannot be submitted, but can be
        # useful with JavaScript.
        name = self.name
        focus = form.addControl(name, True)
        if name is not None:
            default = self.getDefault(form=form, formArgs=formArgs, **kwargs)
            if default is not None and default is not mandatory:
                form.addClearCode(
                    'inputs.%s.value = "%s";' % (
                        name, option.adaptAttributeValue(default)
                        )
                    )

        extraAttribs = self.extraAttribs or {}
        return xhtml.select(
            tabindex=1, name=self.name, autofocus=focus, **extraAttribs
            )[
            _presentOptions(
                self.iterOptions(**kwargs),
                self.getActive(**kwargs)
                )
            ]

    def getActive(self, **kwargs):
        '''Returns the active option, or None if no option is active.
        '''
        raise NotImplementedError

    def getDefault(self, formArgs, **kwargs):
        '''Returns the default option, or None so skip the generation of
        the form clear code.
        The default implementation returns the default value of the form
        argument with the same name as this widget, or None if no default
        could be determined.
        '''
        return _getDefault(formArgs, self.name)

    def iterOptions(self, **kwargs):
        '''Iterates through the multiple choice options.
        Elements can be a string, which is used for both the value and the
        label of the option, a pair of a label and a value string, or a
        pair of a label and sequence of options, which is presented as an
        options group.
        '''
        raise NotImplementedError

def _presentOptions(options, selected, prefix = None):
    '''Generate XHTML for the given options, which can contain nested options.
    Note: This used to be an internal function of DropDownList.present(), but
          recursive inner functions are not collected by the refcounting
          garbage collection, which means a memory leak since we have
          the mark-and-sweep collector turned off.
    '''
    empty = True
    for item in options:
        empty = False
        if iterable(item):
            label, value = item
        else:
            label = value = item
        if iterable(value):
            yield xhtml.optgroup(label = label)[
                _presentOptions(value, selected, label + ',')
                ]
        else:
            if prefix is not None:
                value = prefix + value
            yield xhtml.option(
                value = value,
                selected = value == selected
                )[ label ]
    if empty:
        # Empty <select> or <optgroup> is not allowed by the DTD.
        yield xhtml.option(disabled = True)[ '(list is empty)' ]

class _CheckBox(AttrContainer, XMLPresentable):

    def present(self, *, form, formArgs, **kwargs):
        attributes = self._attributes
        name = attributes.get('name')
        focus = form.addControl(name, True)

        if 'checked' not in attributes and name is not None:
            if formArgs is not None:
                value = getattr(formArgs, name, False)
                if isinstance(value, bool):
                    checked = value
                elif isinstance(value, frozenset):
                    checked = attributes['value'] in value
                else:
                    raise TypeError(type(value))
                if checked:
                    attributes = dict(attributes, checked=True)

        box = xhtml.input(type='checkbox', autofocus=focus, **attributes)
        label = tuple(self._presentContents(
            form=form, formArgs=formArgs, **kwargs
            ))
        return xhtml.label[ box, label ] if label else box

checkBox = _CheckBox((), dict(value='true', tabindex=1))

class CheckBoxesTable(Table):
    name = abstract # type: ClassVar[str]

    def present(self, **kwargs):
        yield super().present(**kwargs)
        # TODO: If there are multiple CheckBoxesTable widgets on
        #       the same page, we now duplicate the script.
        yield _toggleRowScript.present(**kwargs)

    def iterRows(self, form, **kwargs):
        active = self.getActive(form=form, **kwargs)
        first = True
        for key, cells in self.iterOptions(form=form, **kwargs):
            if first:
                focus = form.addControl(self.name, True)
                first = False
            else:
                focus = False
            yield ( cell(
                    class_ = 'clickable',
                    onclick = 'toggleRow(event)'
                    )[
                    xhtml.label[
                        xhtml.input(
                            type = 'checkbox', tabindex = 1,
                            name = self.name, value = key,
                            checked = key in active, autofocus = focus
                            ), ' ', cells[0]
                        ]
                    ],
                ) + tuple(cells[1 : ])

    def getActive(self, **kwargs):
        '''Returns the active options.
        '''
        raise NotImplementedError

    def iterOptions(self, **kwargs):
        '''Iterates through the multiple choice options.
        Each element should be a tuple where the first position contains
        the key belonging to that option and the other positions are
        cell contents.
        '''
        raise NotImplementedError

class SingleCheckBoxTable(CheckBoxesTable):
    '''Special check boxes table which offers only a single check box.
    '''
    name = abstract # type: ClassVar[str]
    columns = None,
    label = abstract # type: ClassVar[str]
    '''Label for the check box.'''

    def iterOptions(self, **kwargs):
        yield 'true', ( self.label, )

    def isActive(self, formArgs, **kwargs):
        '''Returns True iff the single check box is active.
        The default implementation returns the value of the argument that
        matches the submission name of this check boxes table.
        '''
        active = getattr(formArgs, self.name)
        if not isinstance(active, bool):
            raise TypeError(
                'Invalid page argument value type: expected "bool", got "%s"'
                % type(active).__name__
                )
        return active

    def getActive(self, **kwargs):
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
    name = None # type: str
    '''Name is mandatory, but sometimes static and sometimes computed.'''

    def iterRows(self, form, **kwargs):
        formId = form.id
        name = self.name
        active = self.getActive(form=form, **kwargs)
        for index, item in enumerate(self.iterOptions(form=form, **kwargs)):
            focus = index == 0 and form.addControl(name, True)
            key = item[0]
            box = xhtml.input(
                type = 'radio', tabindex = 1, name = name, value = key,
                checked = key == active, autofocus = focus
                )
            yield row(
                # Note: While clicking the label will activate the button,
                #       the JavaScript reacts to the entire row.
                onclick = 'document.forms.%s[\'%s\'][%d].checked=true'
                    % (formId, name, index),
                class_ = 'clickable'
                )[ self.formatOption(box, item[1:]) ]

    def getActive(self, formArgs, **kwargs):
        '''Returns the active option, or None if no option is active.
        The default implementation returns the value of the page argument
        with the same name as this control.
        '''
        return getattr(formArgs, self.name)

    def iterOptions(self, **kwargs):
        '''Iterates through the multiple choice options.
        Each element should be a tuple where the first position contains
        the key belonging to that option and the other positions are
        cell contents.
        '''
        raise NotImplementedError

    def formatOption(self, box, cells):
        '''Formats the given `box` and `cells` into row contents.
        The default implementation puts the radio box into the first column
        with the entire first cell as its label and puts the other cells in
        the remaining columns.
        Each label can contain only one input element, so if your first column
        contains an input other than the radio box, you have to override this
        method.
        '''
        return (xhtml.label[box, ' ', cells[0]], ) + tuple(cells[1:])

class FormTable(Table):
    '''Presents a form as a table, where each row contains a form field.
    '''
    labelStyle = None # type: Optional[str]
    '''CSS class for field label cells.'''
    fieldStyle = None # type: Optional[str]
    '''CSS class for field widget cells.'''
    style = 'properties'

    def iterColumns(self, **kwargs):
        yield Column(None, cellStyle = self.labelStyle)
        yield Column(None, cellStyle = self.fieldStyle)

    def iterRows(self, proc, **kwargs):
        for label, widget in self.iterFields(proc):
            yield label + ':', widget

    def iterFields(self, proc):
        '''Iterates through the fields in this form.
        Each element should be a (label, widget) pair.
        '''
        raise NotImplementedError

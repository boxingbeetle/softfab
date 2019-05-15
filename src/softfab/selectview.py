# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from typing import ClassVar, Iterator

from softfab.Page import Redirect
from softfab.databaselib import Database
from softfab.formlib import (
    disabledButton, dropDownList, hiddenInput, makeForm, resetButton,
    submitButton, textInput
)
from softfab.pageargs import ArgsCorrected, PageArgs, SetArg, StrArg
from softfab.querylib import CustomFilter, runQuery
from softfab.selectlib import TagCache
from softfab.utils import abstract
from softfab.webgui import (
    Column, Table, addRemoveStyleScript, cell, hgroup, pageLink, pageURL,
    preserveSpaces, script
)
from softfab.xmlgen import txt, xhtml


class TagArgs(PageArgs):
    tagkey = StrArg(None)
    tagvalue = StrArg(None)

def textToValues(text):
    '''Splits a comma separated text into a value set.
    '''
    return set(
        value
        for value in ( value.strip() for value in text.split(',') )
        if value
        )

def valuesToText(values):
    return ', '.join(sorted(values))

_selectScript1 = script[
r'''
function setSelection(form, inputName, state) {
    var inputs = form.getElementsByTagName('input');
    for (var i = 0; i < inputs.length; i++) {
        var input = inputs[i];
        if ((input.type == 'checkbox') && (input.name == inputName) &&
            (!input.disabled)) input.checked = state? 'checked': undefined;
    }
}
''']

_selectScript2 = script[
r'''
function setRowStyle(row, input) {
    if (input.checked) {
        addStyle(row, "selected");
    } else {
        removeStyle(row, "selected");
    }
}
function setSelection(form, inputName, state) {
    var rows = form.getElementsByTagName('tr');
    for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var inputs = row.getElementsByTagName('input');
        for (var j = 0; j < inputs.length; j++) {
            var input = inputs[j];
            if ((input.type == 'checkbox') && (input.name == inputName)) {
                input.checked = state? 'checked': undefined;
                setRowStyle(row, input);
            }
        }
    }
}
function RowSelection(formId) {
    this.inputRows = [];
    var form = document.getElementById(formId);
    var rows = form.getElementsByTagName('tr');
    for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var inputs = row.getElementsByTagName('input');
        for (var j = 0; j < inputs.length; j++) {
            var input = inputs[j];
            if ((input.type == 'checkbox') && (input.name == 'sel')) {
                setRowStyle(row, input);
                this.inputRows[input.value] = row;
                this.initEvent(input);
            }
        }
    }
}
//This must be in a separate function, otherwise wrong 'input' is used
function initEvent(input) {
    var owner = this;
    input.onclick = function(event) { owner.rowChanged(input) }
}
function rowChanged(input) {
    setRowStyle(this.inputRows[input.value], input);
}
RowSelection.prototype.rowChanged = initEvent;
RowSelection.prototype.rowChanged = rowChanged;
''']

_resButtonLabel = 'Deselect'
_selButtonLabel = 'Select All'

class SelectArgs(PageArgs):
    # Top form: selected items.
    # Basket form: basket contents when form was generated.
    sel = SetArg()

class BasketArgs(SelectArgs):
    # Items selected in the basket.
    bsk = SetArg()
    # Identifies the submit button that was used.
    action = StrArg(None)

class SelectProcMixin(ABC):
    tagCache = abstract # type: ClassVar[TagCache]
    db = abstract # type: ClassVar[Database]

    def iterActions(self):
        raise NotImplementedError

    def processSelection(self):
        db = self.db
        args = self.args
        tagCache = self.tagCache
        action = args.action
        selected = set(recordId for recordId in args.sel if recordId in db)

        if action == 'remove':
            selected -= args.bsk
        else:
            for value, label_, page in self.iterActions():
                if action == value:
                    raise Redirect(pageURL(
                        page, SelectArgs(sel = selected)
                        ))

        tagKey = None
        tagKeys = tagCache.getKeys()
        if tagKeys:
            tagKey = args.tagkey
            if tagKey is None or not (tagKey == '' or tagKey in tagKeys):
                tagKey = tagKeys[0]

        tagValue = None
        if tagKey:
            tagValue = args.tagvalue
            if tagValue:
                if tagCache.hasValue(tagKey, tagValue):
                    # Known tag, use display value.
                    _, tagValue = tagCache.toCanonical(tagKey, tagValue)
                else:
                    tagValue = None
            if tagValue is None:
                tagValues = tagCache.getValues(tagKey)
                if tagValues:
                    tagValue = tagValues[0]
                else:
                    tagValue = ''

        if (selected != args.sel
        or tagKey != args.tagkey or tagValue != args.tagvalue):
            raise ArgsCorrected(args,
                sel = selected, tagkey = tagKey, tagvalue = tagValue
                )

        filteredRecords = self.filterRecords()

        self.selected = selected
        self.selectedRecords = [ db[recordId] for recordId in selected ]
        self.filtered = set( record.getId() for record in filteredRecords )
        self.filteredRecords = filteredRecords

    def filterRecords(self):
        tagKey = self.args.tagkey
        tagValue = self.args.tagvalue
        tagCache = self.tagCache
        if len(tagCache.getKeys()) == 0 or tagKey == '':
            return self.db
        else:
            if tagValue == '':
                recordFilter = CustomFilter(
                    lambda record: not record.hasTagKey(tagKey)
                    )
            else:
                cvalue, dvalue_ = tagCache.toCanonical(tagKey, tagValue)
                recordFilter = CustomFilter(
                    lambda record: record.hasTagValue(tagKey, cvalue)
                    )
            return runQuery(( recordFilter, ), self.db)

def _scriptButton(select, inputName = 'sel'):
    return xhtml.button(
        type = 'button', tabindex = 1,
        onclick = "setSelection(form, '%s', %s);" % (
            inputName, 'true' if select else 'false'
            )
        )

def selectDialog(proc, formAction, tagCache, filterTable, basketTable, title):
    tagKey = proc.args.tagkey
    tagValue = proc.args.tagvalue
    selected = proc.selected
    filtered = proc.filtered

    cleanedArgs = proc.args.override(
        sel = selected,
        bsk = set(),
        action = None
        )

    yield xhtml.p[
        'Number of %ss shown: %d of %d'
        % ( proc.db.description, len(filtered), len(proc.db) )
        ]

    def actionButtons():
        return [
            submitButton(name = 'action', value = value)[ label ]
            for value, label, action_ in proc.iterActions()
            ]

    tagKeys = tagCache.getKeys()
    if len(tagKeys) == 0:
        yield makeForm(
            formId = 'selform1', action = formAction, method = 'get',
            args = cleanedArgs
            )[
            filterTable,
            addRemoveStyleScript,
            _selectScript2,
            script[
                "window.onload = function() { RowSelection('selform1'); }"
                ],
            xhtml.p[
                txt('\u00A0').join(
                    [    _scriptButton(True)[ _selButtonLabel ],
                        _scriptButton(False)[ _resButtonLabel ],
                        ] + actionButtons()
                    )
                ]
            ].present(
                proc=proc,
                getRowStyle=lambda record: None,
                selectName='sel',
                selectFunc=lambda recordId: (recordId in selected, True)
                )
        return

    def createKeyCell(key):
        label = preserveSpaces(key) if key else '(show all)'
        if key == tagKey:
            return xhtml.td(class_ = 'navthis')[ label ]
        else:
            return xhtml.td(class_ = 'navother')[
                pageLink(
                    formAction, cleanedArgs.override(
                        tagkey = key, tagvalue = None, first = 0
                        )
                    )[ label ]
                ]
    yield xhtml.table(class_ = 'nav')[
        xhtml.tbody[
            xhtml.tr[
                xhtml.th[ 'Tag Keys:' ],
                ( createKeyCell(key) for key in tagKeys + [''] )
                ]
            ]
        ]

    if tagKey == '':
        valueTable = None
    else:
        def createTagCell(value):
            label = preserveSpaces(value) if value else '(undefined)'
            if value == tagValue:
                return xhtml.td(class_ = 'navthis')[ label ]
            else:
                return xhtml.td(class_ = 'navother')[
                    pageLink(
                        formAction, cleanedArgs.override(
                            tagvalue = value, first = 0
                            )
                        )[ label ]
                    ]
        valueTable = xhtml.table(class_ = 'nav')[
            xhtml.tbody[
                xhtml.tr[ xhtml.th[ 'Tag Values:' ] ],
                ( xhtml.tr[ createTagCell(value) ]
                  for value in list(tagCache.getValues(tagKey)) + [''] )
                ]
            ]

    def selectedDisable(recordId):
        sel = recordId in selected
        return sel, not sel
    if filtered - selected:
        buttons = [
            _scriptButton(True)[ _selButtonLabel ],
            resetButton[ _resButtonLabel ],
            submitButton(name = 'action', value = 'add')
            ]
        if not selected:
            buttons += actionButtons()
        setFocus = True
    else:
        buttons = [
            disabledButton[ _selButtonLabel ],
            disabledButton[ _resButtonLabel ],
            disabledButton[ 'Add' ],
            ]
        setFocus = False
    yield makeForm(
        formId = 'selform1', action = formAction, method = 'get',
        args = cleanedArgs, setFocus = setFocus
        )[
        hgroup[ valueTable, filterTable ],
        _selectScript1,
        # Store basket contents.
        # There will be checkboxes named "sel" as well; the results from the
        # active checkboxes will be merged with these hidden fields.
        (hiddenInput(name='sel', value=item) for item in selected),
        xhtml.p[ txt('\u00A0').join(buttons) ]
        ].present(
            proc=proc,
            getRowStyle=lambda record:
                'selected' if record.getId() in selected else None,
            selectName='sel',
            selectFunc=selectedDisable
            )

    if selected:
        yield xhtml.hr
        if title:
            yield xhtml.h2[ title ]
        yield xhtml.p[
            'Number of %ss in basket: %d'
             % ( proc.db.description, len(proc.selectedRecords) )
            ]
        buttons = [
            _scriptButton(True, 'bsk')[ _selButtonLabel ],
            resetButton[ _resButtonLabel ],
            submitButton(name = 'action', value = 'remove')
            ] + actionButtons()
        yield makeForm(
            formId = 'selform2', action = formAction, method = 'get',
            args = cleanedArgs, setFocus = not setFocus
            )[
            basketTable,
            xhtml.p[ txt('\u00A0').join(buttons) ]
            ].present(
                proc=proc,
                getRowStyle=lambda record: 'selected',
                selectName='bsk',
                selectFunc=lambda recordId: (False, True)
                )

class TagValueEditTable(Table, ABC):
    valTitle = 'Tag Values'
    tagCache = abstract # type: ClassVar[TagCache]

    addTagValueScript = script[
        r'''
        function AddTagValue(field, event) {
            var widget = event.target || event.srcElement;
            var value = widget[widget.selectedIndex].value;
            var input = widget.form[field];
            var oldValues = input.value.split(/\s*,\s*/);
            var newValues = new Array();
            var exists = false;
            for (var i = 0; i < oldValues.length; i++) {
                var item = oldValues[i]
                if (item) {
                    if (item != value) {
                        newValues.push(item);
                    } else {
                        exists = true;
                        break;
                    }
                }
            }
            if (!exists) {
                newValues.push(value);
                input.value = newValues.join(', ');
            }
            widget.selectedIndex = 0;
        }
        '''].present()

    def iterColumns(self, **kwargs: object) -> Iterator[Column]:
        yield Column('Tag Key')
        yield Column(self.valTitle)
        yield Column('Add Existing Value')

    def iterRows(self, *, getValues, **kwargs):
        tagKeys = self.tagCache.getKeys()
        for index, key in enumerate(tagKeys):
            indexStr = str(index)
            inputName = 'tagvalues.' + indexStr
            values = self.tagCache.getValues(key)
            yield (
                preserveSpaces(key),
                ( hiddenInput(name='tagkeys.' + indexStr, value=key),
                  textInput(name=inputName, value=getValues(key), size=80) ),
                cell(class_ = 'taglist')[
                    dropDownList(
                        selected='', style='width: 100%',
                        onchange = "AddTagValue('" + inputName + "', event);"
                        )[ [''] + values ]
                    ] if values else cell
                )

    def present(self, **kwargs):
        yield self.addTagValueScript
        yield super().present(**kwargs)

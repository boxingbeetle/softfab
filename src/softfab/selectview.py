# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC, abstractmethod
from itertools import chain
from typing import (
    Callable, ClassVar, Collection, Generic, Iterable, Iterator, List,
    MutableSet, Optional, Sequence, Tuple, TypeVar, cast
)

from softfab.Page import Redirect
from softfab.databaselib import Database
from softfab.formlib import (
    disabledButton, dropDownList, hiddenInput, makeForm, resetButton,
    submitButton, textInput
)
from softfab.pageargs import ArgsCorrected, PageArgs, SetArg, StrArg
from softfab.querylib import CustomFilter, runQuery
from softfab.selectlib import SelectableRecord, SelectableRecordABC, TagCache
from softfab.utils import abstract
from softfab.webgui import (
    Column, Table, addRemoveStyleScript, cell, hgroup, pageLink, pageURL,
    preserveSpaces, script
)
from softfab.xmlgen import XML, XMLContent, XMLNode, xhtml


class TagArgs(PageArgs):
    tagkey = StrArg(None)
    tagvalue = StrArg(None)

def textToValues(text: str) -> MutableSet[str]:
    '''Splits a comma separated text into a value set.
    '''
    return {
        value
        for value in ( value.strip() for value in text.split(',') )
        if value
        }

def valuesToText(values: Iterable[str]) -> str:
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

class BasketArgs(TagArgs, SelectArgs):
    # Items selected in the basket.
    bsk = SetArg()
    # Identifies the submit button that was used.
    action = StrArg(None)

BasketArgsT = TypeVar('BasketArgsT', bound=BasketArgs)

class SelectProcMixin(Generic[BasketArgsT, SelectableRecord]):
    tagCache: ClassVar[TagCache] = abstract

    @property
    @abstractmethod
    def db(self) -> Database[SelectableRecord]:
        raise NotImplementedError

    args: BasketArgsT

    def iterActions(self) -> Iterator[Tuple[str, str, str]]:
        raise NotImplementedError

    def processSelection(self) -> None:
        db = self.db
        args = self.args
        tagCache = self.tagCache
        action = args.action
        selected = {recordId for recordId in args.sel if recordId in db}

        if action == 'remove':
            selected -= args.bsk
        else:
            for value, label_, page in self.iterActions():
                if action == value:
                    raise Redirect(pageURL(
                        page, SelectArgs(sel = selected)
                        ))

        # Determine tag key to filter by.
        # Empty string as key shows all records (all-pass filter).
        tagKey = args.tagkey
        tagKeys = tagCache.getKeys()
        if tagKey and tagKey not in tagKeys:
            # Drop non-existing key.
            tagKey = None
        if tagKey is None and tagKeys:
            # Pick default key.
            tagKey = tagKeys[0]

        # Determine tag value to filter by.
        # Empty string as value shows records that are not tagged
        # with the given tag key.
        if tagKey:
            tagValue = args.tagvalue
            if tagValue:
                if tagCache.hasValue(tagKey, tagValue):
                    # Known tag, use display value.
                    _, tagValue = tagCache.toCanonical(tagKey, tagValue)
                else:
                    # Drop non-existing value.
                    tagValue = None
            if tagValue is None:
                # Pick default value.
                # If nothing is tagged with this key, show untagged.
                tagValue = min(tagCache.getValues(tagKey), default='')
        else:
            # A value only has meaning if we have a key.
            tagValue = None

        if (selected != args.sel or tagKey != args.tagkey
                                 or tagValue != args.tagvalue):
            raise ArgsCorrected(args,
                                sel=selected, tagkey=tagKey, tagvalue=tagValue)

        filteredRecords = self.__filterRecords(tagKey, tagValue)

        self.selected = selected
        self.selectedRecords = [ db[recordId] for recordId in selected ]
        self.filtered = {record.getId() for record in filteredRecords}
        self.filteredRecords = filteredRecords

    def __filterRecords(self, tagKey: Optional[str], tagValue: Optional[str]
                        ) -> Collection[SelectableRecord]:
        if tagKey:
            assert tagValue is not None
            if tagValue:
                cvalue, dvalue_ = self.tagCache.toCanonical(tagKey, tagValue)
                assert cvalue is not None
                # The cast is necessary because mypy seems to ignore
                # the narrowed type in the parameter default value.
                #   https://github.com/python/mypy/issues/2608
                def valueFilter(record: SelectableRecord,
                                tagKey: str = cast(str, tagKey),
                                cvalue: str = cvalue
                                ) -> bool:
                    return record.tags.hasTagValue(tagKey, cvalue)
                recordFilter = CustomFilter(valueFilter)
            else:
                def keyFilter(record: SelectableRecord,
                              tagKey: str = cast(str, tagKey)
                              ) -> bool:
                    return not record.tags.hasTagKey(tagKey)
                recordFilter = CustomFilter(keyFilter)
            return runQuery(( recordFilter, ), self.db)
        else:
            return self.db

def _scriptButton(select: bool, inputName: str = 'sel') -> XMLNode:
    return xhtml.button(
        type = 'button', tabindex = 1,
        onclick = f"setSelection(form, '{inputName}', "
                               f"{'true' if select else 'false'});"
        )

def selectDialog(formAction: str,
                 tagCache: TagCache,
                 filterTable: XMLContent,
                 basketTable: XMLContent,
                 title: str,
                 **kwargs: object
                 ) -> Iterator[XML]:
    proc = cast(SelectProcMixin[BasketArgs, SelectableRecordABC],
                kwargs['proc'])
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
        f'Number of {proc.db.description}s shown: '
        f'{len(filtered):d} of {len(proc.db):d}'
        ]

    def actionButtons() -> List[XMLContent]:
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
                xhtml['\u00A0'].join(chain(
                    [ _scriptButton(True)[ _selButtonLabel ],
                      _scriptButton(False)[ _resButtonLabel ] ],
                    actionButtons()
                    ))
                ]
            ].present(
                getRowStyle=lambda record: None,
                selectName='sel',
                selectFunc=lambda recordId: (recordId in selected, True),
                **kwargs
                )
        return

    def createKeyCell(key: str) -> XML:
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
                ( createKeyCell(key) for key in chain(tagKeys, ['']) )
                ]
            ]
        ]

    if tagKey:
        def createTagCell(value: str) -> XML:
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
        valueTable: XMLContent = xhtml.table(class_ = 'nav')[
            xhtml.tbody[
                xhtml.tr[ xhtml.th[ 'Tag Values:' ] ],
                ( xhtml.tr[ createTagCell(value) ]
                  for value in sorted(tagCache.getValues(tagKey)) + [''] )
                ]
            ]
    else:
        valueTable = None

    def selectedDisable(recordId: str) -> Tuple[bool, bool]:
        sel = recordId in selected
        return sel, not sel
    if filtered - selected:
        buttons: List[XMLContent] = [
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
    def rowStyle(record: SelectableRecord) -> Optional[str]:
        return 'selected' if record.getId() in selected else None
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
        xhtml.p[ xhtml['\u00A0'].join(buttons) ]
        ].present(
            getRowStyle=rowStyle,
            selectName='sel',
            selectFunc=selectedDisable,
            **kwargs
            )

    if selected:
        yield xhtml.hr
        yield xhtml.h2[ title ]
        yield xhtml.p[
            f'Number of {proc.db.description}s in basket: '
            f'{len(proc.selectedRecords):d}'
            ]
        yield makeForm(
            formId = 'selform2', action = formAction, method = 'get',
            args = cleanedArgs, setFocus = not setFocus
            )[
            basketTable,
            xhtml.p[
                xhtml['\u00A0'].join(chain(
                    [ _scriptButton(True, 'bsk')[ _selButtonLabel ],
                      resetButton[ _resButtonLabel ],
                      submitButton(name = 'action', value = 'remove') ],
                    actionButtons()
                    ))
                ]
            ].present(
                getRowStyle=lambda record: 'selected',
                selectName='bsk',
                selectFunc=lambda recordId: (False, True),
                **kwargs
                )

class TagValueEditTable(Table, ABC):
    valTitle = 'Tag Values'
    tagCache: ClassVar[TagCache] = abstract

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

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        getValues = cast(Callable[[str], Sequence[str]], kwargs['getValues'])
        tagKeys = self.tagCache.getKeys()
        for index, key in enumerate(tagKeys):
            indexStr = str(index)
            inputName = 'tagvalues.' + indexStr
            values = sorted(self.tagCache.getValues(key))
            yield (
                preserveSpaces(key),
                ( hiddenInput(name='tagkeys.' + indexStr, value=key),
                  textInput(name=inputName, value=getValues(key), size=80) ),
                cell(class_ = 'taglist')[
                    dropDownList(
                        selected='', style='width: 100%',
                        onchange = "AddTagValue('" + inputName + "', event);"
                        )[ chain([''], values) ]
                    ] if values else cell
                )

    def present(self, **kwargs: object) -> XMLContent:
        yield self.addTagValueScript
        yield super().present(**kwargs)

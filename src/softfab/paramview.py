# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import (
    Dict, Iterable, Iterator, Mapping, Optional, Set, Tuple, cast
)
import re

from softfab.Page import PageProcessor, PresentableError
from softfab.formlib import RadioTable, checkBox, hiddenInput, textInput
from softfab.pageargs import BoolArg, DictArg, EnumArg, PageArgs, StrArg
from softfab.paramlib import ParamMixin, specialParameters
from softfab.taskdeflib import TaskDef
from softfab.webgui import Table, cell, rowManagerInstanceScript, script
from softfab.xmlgen import XMLContent, xhtml

reParamName = re.compile(r'^(?:sf\.|[A-Za-z_])[A-Za-z_0-9]*$')
'''Regular expression which defines valid parameter names.
'''

SummaryType = Enum('SummaryType', 'INHERIT NONE FILE DIR')
'''Available ways to provide a report summary.
'''

class ParamArgsMixin:
    '''Adds parameter editing arguments to a page.'''

    params = DictArg(StrArg())
    values = DictArg(StrArg())
    final = DictArg(BoolArg())
    poverride = DictArg(BoolArg())

    # These are the fields for the user-friendly report summary input.
    # In validateParamState() we translate this into "sf.summary".
    summary = EnumArg(SummaryType, SummaryType.INHERIT)
    summaryfile = StrArg('')
    summarydir = StrArg('')

class _ParamArgs:
    """Helper class for type checking."""
    params = Dict[str, str]()
    values = Dict[str, str]()
    final = Dict[str, bool]()
    poverride = Dict[str, bool]()
    summary = SummaryType.INHERIT
    summaryfile = ''
    summarydir = ''

def _namePresentation(name: str) -> str:
    if name == 'sf.summary':
        return 'Summary report'
    else:
        return name

def _valuePresentation(name: str, value: str) -> str:
    if name == 'sf.summary':
        return _summaryValuePresentation(value)
    else:
        return value

def _summaryValuePresentation(value: str) -> str:
    if value == '':
        return 'none'
    elif value.endswith('/'):
        return 'directory: ' + value
    else:
        return 'file: ' + value

class ParamCell(RadioTable):
    style = 'hollow'
    columns = None, None

    def __init__(self, key: str, value: str, parentValue: str):
        RadioTable.__init__(self)
        self.__key = key
        self.__value = value
        self.__parentValue = parentValue
        self.name = 'poverride.' + key

    def getActive(self, **kwargs: object) -> Optional[str]:
        args = cast(_ParamArgs, kwargs['formArgs'])
        return str(args.poverride.get(self.__key, False)).lower()

    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[str, str, XMLContent]]:
        parentValue = self.__parentValue
        if parentValue == '':
            parentValue = '(empty)'
        yield 'false', '\u00A0Inherit\u00A0', parentValue
        yield 'true', '\u00A0Override\u00A0', textInput(
            name='values.' + self.__key, value=self.__value, size=72,
            # The onchange event handler is there to make sure the right
            # radio button is activated when text is pasted into the edit
            # box from the context menu (right mouse button).
            onchange="form['%s'][1].checked=true" % self.name
            )

class ParamOverrideTable(Table):
    columns = 'Task', 'Parameter', 'Value'
    hideWhenEmpty = True
    suppressedParams = 'sf.summary',

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        # Sort tasks by name (first element in tuple).
        tasks = cast(
            Iterable[Tuple[str, TaskDef, Mapping[str, str]]],
            kwargs['tasks']
            )
        sortedTasks = sorted(tasks)

        for taskId, taskDef, taskParams in sortedTasks:
            tableRows = []
            sortedParams = sorted(
                ( name, value )
                for name, value in taskDef.getParameters().items()
                if name not in self.suppressedParams
                )
            for name, defValue in sortedParams:
                if not taskDef.isFinal(name):
                    curValue = taskParams.get(name, '')
                    tableRows.append([
                        name,
                        self.getParamCell(taskId, name, curValue, defValue,
                                          **kwargs)
                        ])
            if len(tableRows) > 0:
                tableRows[0].insert(0, cell(rowspan = len(tableRows))[taskId])
                yield from tableRows

    def getParamCell(self,
                     taskId: str,
                     name: str,
                     curValue: str,
                     defValue: str,
                     **kwargs: object
                     ) -> XMLContent:
        raise NotImplementedError

class SummaryParamCell(RadioTable):
    style = 'hollow summaryparam'
    columns = None, None

    def __init__(self, key: str, value: str, parentValue: str):
        RadioTable.__init__(self)
        self.__key = key
        self.__value = value
        self.__parentValue = parentValue
        self.name = 'summary'

    def getActive(self, **kwargs: object) -> SummaryType:
        args = cast(_ParamArgs, kwargs['formArgs'])
        if not args.poverride.get(self.__key, False):
            return SummaryType.INHERIT
        elif self.__value == '':
            return SummaryType.NONE
        elif self.__value.endswith('/'):
            return SummaryType.DIR
        else:
            return SummaryType.FILE

    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[SummaryType, str, XMLContent]]:
        if self.__value.endswith('/'):
            fileValue = ''
            dirValue = self.__value
        else:
            fileValue = self.__value
            dirValue = ''
        yield SummaryType.INHERIT, '\u00A0Inherit\u00A0', \
            _summaryValuePresentation(self.__parentValue)
        yield SummaryType.NONE, '\u00A0None\u00A0', '(no Report Summary tab)'
        yield SummaryType.FILE, '\u00A0File\u00A0', textInput(
            name='summaryfile', value=fileValue, size=72,
            onchange="form['%s'][2].checked=true" % self.name
            )
        yield SummaryType.DIR, '\u00A0Directory\u00A0', textInput(
            name='summarydir', value=dirValue, size=72,
            onchange="form['%s'][3].checked=true" % self.name
            )

class ParamDefTable(Table):
    columns = 'Parameter', 'Value', 'Final'
    bodyId = 'paramList'

    initRowIndicesScript = script[r'''
function initRowIndices(node, index) {
    visitRow(node, function(item) {
        var dot = item.name.lastIndexOf('.');
        item.name = item.name.substring(0, dot + 1) + index;
        })
}
''']

    def __init__(self, parent: ParamMixin):
        super().__init__()
        self.__parentParams = parent.getParameters()

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        args = cast(_ParamArgs, kwargs['formArgs'])
        parentParams = self.__parentParams
        valueFieldAttribs = {} # type: Mapping[str, str]
        for index in [ str(i) for i in range(len(args.params) + 1) ]:
            name = args.params.get(index, '')
            value = args.values.get(index, '')
            final = args.final.get(index, False)
            if name in parentParams:
                valueWidget = SummaryParamCell if name == 'sf.summary' \
                                               else ParamCell
                nameField = (
                    _namePresentation(name),
                    hiddenInput(name='params.' + index, value=name)
                    ) # type: XMLContent
                valueField = valueWidget(
                    index, value, parentParams[name]
                    ).present(**kwargs)
                # The value text box for new parameters that will follow the
                # parent parameters should be stretched to fill the entire
                # cell, otherwise the layout looks ugly.
                # However, we cannot specify "width:100%" always since IE will
                # narrow the text box to the size of the column header if there
                # are no parent params.
                valueFieldAttribs = { 'style': 'width:100%' }
            else:
                nameField = textInput(
                    name='params.' + index, value=name, size=20
                    )
                valueField = textInput(
                    name='values.' + index, value=value, size=72,
                    **valueFieldAttribs
                    )
            yield (
                nameField,
                valueField,
                checkBox(name='final.' + index, checked = final)
                )

    def present(self, **kwargs: object) -> XMLContent:
        args = cast(_ParamArgs, kwargs['formArgs'])
        numParams = len(
            set(args.params.values()) & set(self.__parentParams)
            )
        yield xhtml.h2[ 'Parameters' ]
        yield super().present(**kwargs)
        yield self.initRowIndicesScript.present(**kwargs)
        yield rowManagerInstanceScript(
            bodyId=self.bodyId,
            rowStart=numParams,
            initRow='initRowIndices'
            ).present(**kwargs)
        yield xhtml.ul[
            xhtml.li[
                'Parameters will be passed as variables to the wrapper.'
                ],
            xhtml.li[
                'To delete a parameter, empty the parameter name field.'
                ],
            xhtml.li[
                'Check "Final" if you want to prevent this value from '
                'being overridden.'
                ]
            ]

class ParametersTable(Table):
    hideWhenEmpty = True
    columns = None, None, None, None
    style = 'hollow'

    def __init__(self, fieldName: str):
        Table.__init__(self)
        self.__fieldName = fieldName

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        obj = cast(ParamMixin, getattr(kwargs['proc'], self.__fieldName))
        parameters = set(obj.getParameters()) - specialParameters
        reservedParameters = set(
            param for param in parameters if param.startswith('sf.')
            )
        customParameters = parameters - reservedParameters
        for name in sorted(reservedParameters) + sorted(customParameters):
            value = obj.getParameter(name)
            yield (
                ( _namePresentation(name), '\u00A0' ),
                ( '=\u00A0' ),
                ( _valuePresentation(name, value or ''), '\u00A0' ),
                '(final)' if obj.isFinal(name) else ''
                )

def addParamsToElement(element: ParamMixin, args: ParamArgsMixin) -> None:
    args_ = cast(_ParamArgs, args)
    for index, name in args_.params.items():
        value = (
            args_.values.get(index, '')
            if args_.poverride.get(index)
            else None
            )
        element.addParameter(name, value, args_.final.get(index, False))

def initParamArgs(element: ParamMixin) -> Mapping[str, object]:
    # Note: Only parameters of this task def are considered part of
    #       the editing state, not the parameters of its parents.
    overriddenParams = element.getParametersSelf()
    finalParams = element.getFinalSelf()
    names = (set(overriddenParams) | finalParams) - specialParameters

    summaryVal = overriddenParams.get('sf.summary')
    if summaryVal is None:
        summaryType = SummaryType.INHERIT
    elif summaryVal == '':
        summaryType = SummaryType.NONE
    elif summaryVal.endswith('/'):
        summaryType = SummaryType.DIR
    else:
        summaryType = SummaryType.FILE

    # We rely on validateParamState to put everything in the right order.
    return dict(
        params = { str(index): name for index, name in enumerate(names) },
        values = { str(index): overriddenParams.get(name, '')
            for index, name in enumerate(names) },
        final = { str(index): name in finalParams
            for index, name in enumerate(names) },
        poverride = { str(index): name in overriddenParams
            for index, name in enumerate(names) },
        summary = summaryType,
        summaryfile = summaryVal if summaryType is SummaryType.FILE else '',
        summarydir = summaryVal if summaryType is SummaryType.DIR else '',
        )

def checkParamState(args: ParamArgsMixin, parent: ParamMixin) -> None:
    usedParams = set() # type: Set[str]
    for param in cast(_ParamArgs, args).params.values():
        if param == '':
            continue
        elif reParamName.match(param) is None:
            raise PresentableError(xhtml.p[
                'Invalid parameter name: "%s"' % param
                ])
        elif param in specialParameters:
            raise PresentableError(xhtml.p[
                'Reserved parameter name: "%s"' % param
                ])
        elif param in usedParams:
            raise PresentableError(xhtml.p[
                'Duplicate parameter name: "%s"' % param
                ])
        elif parent.isFinal(param):
            raise PresentableError(xhtml.p[
                'Cannot override final parameter "%s"' % param
                ])
        usedParams.add(param)

def validateParamState(proc: PageProcessor, parent: ParamMixin) -> None:
    args = cast(_ParamArgs, proc.args)

    parentParams = dict(
        ( name, value )
        for name, value in parent.getParameters().items()
        # Only consider overridable parameters.
        # Note that checkParamState() has already rejected attempts
        # to override final parameters.
        if not parent.isFinal(name)
        )

    # Extract the essential data:
    # - maps parameter name to (value, final) pair
    # - a parameter that is present in this dictionary is new or overridden,
    #   an inherited parameter is omitted from the dictionary
    # - parameters with empty name are removed
    # - duplicate parameters are silently reduced to one
    data = {} # type: Dict[str, Tuple[Optional[str], bool]]
    for indexStr, name in args.params.items():
        if name != '':
            value = args.values[indexStr] # type: Optional[str]
            final = args.final.get(indexStr, False)
            if name in parentParams and not args.poverride.get(indexStr):
                value = None # inherited
            data[name] = (value, final)

    if 'sf.summary' in data:
        summaryType = args.summary
        if summaryType is SummaryType.NONE:
            summary = '' # type: Optional[str]
        elif summaryType is SummaryType.FILE:
            summary = args.summaryfile
        elif summaryType is SummaryType.DIR:
            summary = args.summarydir.rstrip('/') + '/'
        elif summaryType is SummaryType.INHERIT:
            summary = None
        else:
            assert False, summaryType
        final = data['sf.summary'][1]
        data['sf.summary'] = ( summary, final )

    # Create new ordering:
    # - first parent params, then new params;
    #   inside these categories params are sorted alphabetically
    names = [
        ( 0, name ) for name in parentParams.keys()
        if name not in specialParameters
        ] + [
        ( 1, name ) for name, (value, final) in data.items()
        if name not in parentParams
            and name not in specialParameters
            and value is not None
        ]
    names.sort()

    params = {}
    values = {}
    finals = {}
    poverride = {}
    for index, (_, name) in enumerate(names):
        strIndex = str(index)
        params[strIndex] = name
        if name in data:
            value, final = data[name]
            if value is None:
                values[strIndex] = ''
                poverride[strIndex] = False
            else:
                values[strIndex] = value
                poverride[strIndex] = True
        else:
            value, final = parentParams[name], False
            values[strIndex] = ''
            poverride[strIndex] = False
        if final:
            finals[strIndex] = True
    proc.args = cast(PageArgs, args).override(
        params = params, values = values, final = finals, poverride = poverride
        )

# SPDX-License-Identifier: BSD-3-Clause

from typing import (
    TYPE_CHECKING, Dict, Iterable, Iterator, Mapping, Optional, Set, Tuple,
    cast
)
import re

from softfab.Page import PageProcessor, PresentableError
from softfab.formlib import RadioTable, checkBox, hiddenInput, textInput
from softfab.pageargs import BoolArg, DictArg, PageArgs, StrArg
from softfab.paramlib import ParamMixin, Parameterized, specialParameters
from softfab.taskdeflib import TaskDef
from softfab.webgui import Table, cell, rowManagerInstanceScript, script
from softfab.xmlgen import XMLContent, xhtml

reParamName = re.compile(r'^(?:sf\.|[A-Za-z_])[A-Za-z_0-9]*$')
'''Regular expression which defines valid parameter names.
'''

class ParamArgsMixin:
    '''Adds parameter editing arguments to a page.'''

    params = DictArg(StrArg())
    values = DictArg(StrArg())
    final = DictArg(BoolArg())
    poverride = DictArg(BoolArg())

class _ParamArgs:
    """Helper class for type checking."""
    if TYPE_CHECKING:
        params = Dict[str, str]()
        values = Dict[str, str]()
        final = Dict[str, bool]()
        poverride = Dict[str, bool]()

# Note: We have the ability to present certain reserved parameters
#       in a special way. The only parameter that used this was removed,
#       but the mechanism going to stay for the time being, under the
#       assumption we might need it again.

def _namePresentation(name: str) -> str:
    return name

def _valuePresentation(name: str, # pylint: disable=unused-argument
                       value: str
                       ) -> str:
    return value

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
        yield 'false', 'Inherit\u00A0', parentValue
        yield 'true', 'Override\u00A0', textInput(
            name='values.' + self.__key, value=self.__value, size=72,
            # The onchange event handler is there to make sure the right
            # radio button is activated when text is pasted into the edit
            # box from the context menu (right mouse button).
            onchange=f"form['{self.name}'][1].checked=true"
            )

class ParamOverrideTable(Table):
    columns = 'Task', 'Parameter', 'Value'
    hideWhenEmpty = True
    suppressedParams = ()

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

    def __init__(self, parent: Parameterized):
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
                nameField = (
                    _namePresentation(name),
                    hiddenInput(name='params.' + index, value=name)
                    ) # type: XMLContent
                valueField = ParamCell(
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
        yield xhtml.h3[ 'Parameters' ]
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
        obj = cast(Parameterized, getattr(kwargs['proc'], self.__fieldName))
        parameters = set(obj.getParameters()) - specialParameters
        reservedParameters = {
            param for param in parameters if param.startswith('sf.')
            }
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

    # We rely on validateParamState to put everything in the right order.
    return dict(
        params = { str(index): name for index, name in enumerate(names) },
        values = { str(index): overriddenParams.get(name, '')
            for index, name in enumerate(names) },
        final = { str(index): name in finalParams
            for index, name in enumerate(names) },
        poverride = { str(index): name in overriddenParams
            for index, name in enumerate(names) },
        )

def checkParamState(args: ParamArgsMixin, parent: Parameterized) -> None:
    usedParams = set() # type: Set[str]
    for param in cast(_ParamArgs, args).params.values():
        if param == '':
            continue
        elif reParamName.match(param) is None:
            raise PresentableError(xhtml.p[
                f'Invalid parameter name: "{param}"'
                ])
        elif param in specialParameters:
            raise PresentableError(xhtml.p[
                f'Reserved parameter name: "{param}"'
                ])
        elif param in usedParams:
            raise PresentableError(xhtml.p[
                f'Duplicate parameter name: "{param}"'
                ])
        elif parent.isFinal(param):
            raise PresentableError(xhtml.p[
                f'Cannot override final parameter "{param}"'
                ])
        usedParams.add(param)

def validateParamState(proc: PageProcessor, parent: Parameterized) -> None:
    args = cast(_ParamArgs, proc.args)

    parentParams = {
        name: value
        for name, value in parent.getParameters().items()
        # Only consider overridable parameters.
        # Note that checkParamState() has already rejected attempts
        # to override final parameters.
        if not parent.isFinal(name)
        }

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

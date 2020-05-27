# SPDX-License-Identifier: BSD-3-Clause

from typing import (
    AbstractSet, ClassVar, Iterator, Optional, Set, TypeVar, cast
)

from softfab.Page import PageProcessor
from softfab.databaselib import Database
from softfab.formlib import (
    clearButton, dropDownList, emptyOption, makeForm, option, resetButton,
    selectionList, submitButton, textInput
)
from softfab.joblib import jobDB
from softfab.pageargs import ArgsCorrected
from softfab.pagelinks import ExecutionState, ReportArgs
from softfab.projectlib import project
from softfab.querylib import CustomFilter, RecordFilter, SetFilter
from softfab.request import Request
from softfab.timeview import formatTime
from softfab.userlib import User, UserDB
from softfab.utils import SharedInstance, abstract
from softfab.webgui import script
from softfab.xmlgen import XMLContent, XMLPresentable, xhtml


def executionStateBox(objectName: str) -> XMLPresentable:
    return dropDownList(name='execState', style='width:20ex')[(
        option(value=state)[f'{state.name.lower()} {objectName}']
        for state in ExecutionState
        )]

def timeValue(seconds: Optional[int]) -> str:
    return '' if seconds is None else formatTime(seconds)

# Note: In the UI (args and form), an absent value is represented by
#       the empty string, but in the DB it is represented by None.

noneOption = emptyOption[ '(none)' ]

def noneToEmpty(values: AbstractSet[Optional[str]]) -> AbstractSet[str]:
    """Replaces a None value with empty string.
    """
    if None in values:
        newValues = set(values)
        newValues.remove(None)
        newValues.add('')
        return cast(Set[str], newValues)
    else:
        return cast(AbstractSet[str], values)

def emptyToNone(values: AbstractSet[str]) -> AbstractSet[Optional[str]]:
    """Replaces a None value with empty string.
    """
    if '' in values:
        newValues: Set[Optional[str]] = set(values)
        newValues.remove('')
        newValues.add(None)
        return newValues
    else:
        return values

ReportArgsT = TypeVar('ReportArgsT', bound=ReportArgs)

class ReportProcessor(PageProcessor[ReportArgsT]):
    db: ClassVar[Optional[Database]] = None
    userDB: ClassVar[UserDB]

    async def process(self, req: Request[ReportArgsT], user: User) -> None:
        # Set of targets for which jobs have run.
        targets = cast(AbstractSet[Optional[str]], jobDB.uniqueValues('target'))
        # Add targets that are available now.
        targets |= project.getTargets()
        uiTargets = noneToEmpty(targets)

        # Set of users that have initiated jobs.
        owners = cast(AbstractSet[Optional[str]], jobDB.uniqueValues('owner'))
        # Add users that are available now.
        owners |= self.userDB.keys()
        uiOwners = noneToEmpty(owners)

        # Reject unknown targets and/or owners.
        if req.args.target - uiTargets or req.args.owner - uiOwners:
            raise ArgsCorrected(req.args.override(
                target=req.args.target & uiTargets,
                owner=req.args.owner & uiOwners
                ))

        # pylint: disable=attribute-defined-outside-init
        self.targets = targets
        self.uiTargets = uiTargets
        self.owners = owners
        self.uiOwners = uiOwners

    def iterFilters(self) -> Iterator[RecordFilter]:
        cTimeAboveInt = self.args.ctabove
        cTimeBelowInt = self.args.ctbelow

        if cTimeAboveInt is not None:
            if cTimeBelowInt is not None:
                yield CustomFilter(lambda record:
                    cTimeAboveInt <= record['timestamp'] <= cTimeBelowInt
                    )
            else:
                yield CustomFilter(lambda record:
                    cTimeAboveInt <= record['timestamp']
                    )
        elif cTimeBelowInt is not None:
            yield CustomFilter(lambda record:
                record['timestamp'] <= cTimeBelowInt
                )

        # TODO: These casts are lies.
        #       None is not Comparable and that is an issue while sorting;
        #       querylib works around that by mapping None to Missing.
        #       However, the type annotations aren't aware of that.
        #       I think the best solution would be to use Missing in all
        #       cases in which records don't have a value for a particular
        #       key, but that is a big change that I don't want to make
        #       right now.

        if self.args.target:
            yield SetFilter.create(
                'target',
                cast(AbstractSet[str], emptyToNone(self.args.target)),
                cast(AbstractSet[str], self.targets),
                self.db
                )

        if self.args.owner:
            yield SetFilter.create(
                'owner',
                cast(AbstractSet[str], emptyToNone(self.args.owner)),
                cast(AbstractSet[str], self.owners),
                self.db
                )

class JobReportProcessor(ReportProcessor[ReportArgsT]):
    db = jobDB

    def iterFilters(self) -> Iterator[RecordFilter]:
        yield from super().iterFilters()
        execState = self.args.execState
        if execState is ExecutionState.COMPLETED:
            yield CustomFilter(lambda record: record.isCompleted())
        elif execState is ExecutionState.FINISHED:
            yield CustomFilter(lambda record: record.hasFinalResult())
        elif execState is ExecutionState.UNFINISHED:
            yield CustomFilter(lambda record: not record.hasFinalResult())

class ReportFilterForm:
    instance: ClassVar = SharedInstance()
    objectName: ClassVar[str] = abstract

    def present(self, **kwargs: object) -> XMLContent:
        yield makeForm(method='get', formId='filters',
                       onsubmit='return checkFilters()')[
            xhtml.table(class_ = 'filters')[
                xhtml.tbody[ self.presentRows(**kwargs) ]
                ]
            ].present(**kwargs)
        yield self.dateCheckScript.present(**kwargs)

    def presentRows(self, **kwargs: object) -> XMLContent:
        proc = cast(ReportProcessor, kwargs['proc'])
        numListItems = cast(int, kwargs['numListItems'])

        targets = proc.uiTargets
        owners = proc.uiOwners
        showOwners = proc.userDB.showOwners
        objectName = self.objectName

        def columns1() -> XMLContent:
            yield xhtml.td(colspan=4)[
                f'Select {objectName} to display reports for:'
                ]
            if len(targets) > 1:
                yield xhtml.td[ 'Targets:' ]
            if len(owners) > 1 and showOwners:
                yield xhtml.td[ 'Owners:' ]
        yield xhtml.tr[ columns1() ]

        def columns2() -> XMLContent:
            yield self.presentCustomBox(**kwargs)
            if len(targets) > 1:
                yield xhtml.td(rowspan=4, style='vertical-align:top')[
                    selectionList(name='target',
                                  size=numListItems,
                                  style='width: 18ex'
                                  )[
                        (target or noneOption for target in sorted(targets))
                        ]
                    ]
            if len(owners) > 1 and showOwners:
                yield xhtml.td(rowspan=4, style='vertical-align:top')[
                    selectionList(name='owner',
                                  size=numListItems,
                                  style='width: 18ex'
                                  )[
                        (owner or noneOption for owner in sorted(owners))
                        ]
                    ]
        yield xhtml.tr[ columns2() ]

        yield xhtml.tr[
            xhtml.td[ 'Created after:' ],
            xhtml.td[
                textInput(
                    name='ctabove', value=timeValue(proc.args.ctabove),
                    style='width:20ex'
                    )
                ],
            xhtml.td[ 'Created before:' ],
            xhtml.td[
                textInput(
                    name='ctbelow', value=timeValue(proc.args.ctbelow),
                    style='width:20ex'
                    )
                ]
            ]

        yield xhtml.tr[
            xhtml.td[ 'Execution state:' ],
            xhtml.td(colspan = 3)[
                executionStateBox(objectName)
                ]
            ]

        yield xhtml.tr[xhtml.td(colspan = 4, style = 'text-align:center')[
            submitButton[ 'Apply' ], ' ', resetButton, ' ', clearButton
            ]]

    def presentCustomBox(self, **kwargs: object) -> XMLContent:
        raise NotImplementedError

    dateCheckScript = script[r'''
var numOfDays = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
function checkMatch(match) {
    if (match == null)
        return false;
    var day = parseInt(match[4], 10);
    if (day > 28) {
        var month = parseInt(match[3], 10);
        if (day > numOfDays[month]) {
            if ((month != 2) || (day > 29))
                return false;
            if ((parseInt(match[1], 10) % 4) > 0)
                return false;
        }
    }
    return true;
}
function checkFilters() {
    if (RegExp) {
        var ctabove = document.forms.filters.elements.ctabove.value;
        var ctbelow = document.forms.filters.elements.ctbelow.value;
        if ((ctabove.length > 0) || (ctbelow.length > 0)) {
            var re = new RegExp('^\\s*((?:20)?\\d\\d)([-./])(0?[1-9]|1[0-2])\\2(0?[1-9]|[12]\\d|3[01])(?:\\s+(?:[01]?\\d|2[0-3])[:.][0-5]\\d)?\\s*$');
            if (ctabove.length > 0) {
                if (!checkMatch(re.exec(ctabove))) {
                    alert('Invalid date/time: ' + ctabove);
                    return false;
                }
            }
            if (ctbelow.length > 0) {
                if (!checkMatch(re.exec(ctbelow))) {
                    alert('Invalid date/time: ' + ctbelow);
                    return false;
                }
            }
        }
    }
    return true;
}
''']

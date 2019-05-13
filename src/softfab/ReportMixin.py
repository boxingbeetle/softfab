# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import ClassVar, Iterator, Optional

from softfab.CSVPage import CSVPage
from softfab.Page import PageProcessor
from softfab.databaselib import Database
from softfab.formlib import (
    clearButton, dropDownList, makeForm, option, resetButton, selectionList,
    submitButton, textInput
)
from softfab.joblib import jobDB
from softfab.pageargs import DateTimeArg, EnumArg, PageArgs, SetArg
from softfab.pagelinks import TaskIdSetArgs
from softfab.projectlib import project
from softfab.querylib import CustomFilter, RecordFilter, SetFilter
from softfab.timeview import formatTime
from softfab.userlib import userDB
from softfab.utils import SharedInstance, abstract
from softfab.webgui import script
from softfab.xmlgen import xhtml


class ExecutionState(Enum):
    ALL = 1
    COMPLETED = 2
    FINISHED = 3
    UNFINISHED = 4

class ReportArgs(PageArgs):
    ctabove = DateTimeArg(None)
    ctbelow = DateTimeArg(None, True)
    execState = EnumArg(ExecutionState, ExecutionState.ALL)
    target = SetArg()
    owner = SetArg()

class ReportTaskArgs(ReportArgs, TaskIdSetArgs):
    pass

class ReportTaskCSVArgs(ReportTaskArgs, CSVPage.Arguments):
    pass

def executionStateBox(objectName):
    return dropDownList(name='execState', style='width:20ex')[(
        option(value=state)['%s %s' % (state.name.lower(), objectName)]
        for state in ExecutionState
        )]

def timeValue(seconds: Optional[int]) -> str:
    return '' if seconds is None else formatTime(seconds)

class ReportProcessor(PageProcessor):
    db = None # type: Optional[Database]

    def process(self, req, user):
        # Set of targets for which jobs have run.
        targets = jobDB.uniqueValues('target') - set([None])
        # Add targets that are available now.
        targets |= project.getTargets()
        # Make a set of targets that should be shown, valid targets only.
        targetFilter = req.args.target & targets

        # None is presented as "(none)" in the UI.
        ownerFilter = set(req.args.owner)
        if '(none)' in ownerFilter:
            ownerFilter.remove('(none)')
            ownerFilter.add(None)
        # Set of users that have initiated jobs.
        owners = jobDB.uniqueValues('owner')
        # Add users that are available now.
        owners |= userDB.keys()
        # Make a set of owners that should be shown, valid owners only.
        ownerFilter &= owners

        # pylint: disable=attribute-defined-outside-init
        self.targets = targets
        self.targetFilter = targetFilter
        self.owners = owners
        self.ownerFilter = ownerFilter

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

        if self.targetFilter:
            yield SetFilter.create(
                'target', self.targetFilter, self.targets, self.db
                )

        if self.ownerFilter:
            yield SetFilter.create(
                'owner', self.ownerFilter, self.owners, self.db
                )

class JobReportProcessor(ReportProcessor):
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
    instance = SharedInstance() # type: ClassVar
    objectName = abstract # type: ClassVar[str]

    def present(self, *, proc, **kwargs):
        yield makeForm(
            method = 'get', formId = 'filters', args = proc.args,
            onsubmit = 'return checkFilters()'
            )[
            xhtml.table(class_ = 'filters')[
                xhtml.tbody[ self.presentRows(proc, **kwargs) ]
                ]
            ].present(proc=proc, **kwargs)
        yield self.dateCheckScript.present(proc=proc, **kwargs)

    def presentRows(self, proc, numListItems, **kwargs):
        targets = proc.targets
        owners = proc.owners
        objectName = self.objectName

        def columns1():
            yield xhtml.td(colspan = 4)[
                'Select %s to display reports for:' % objectName
                ]
            if targets:
                yield xhtml.td[ 'Targets:' ]
            if len(owners) > 1 and project.showOwners:
                yield xhtml.td[ 'Owners:' ]
        yield xhtml.tr[ columns1() ]

        def columns2():
            yield self.presentCustomBox(
                proc=proc, numListItems=numListItems, **kwargs
                )
            if targets:
                yield xhtml.td(rowspan = 4, style = 'vertical-align:top')[
                    selectionList(
                        name='target', size=numListItems, style='width: 18ex',
                        selected=proc.targetFilter
                        )[ sorted(targets) ]
                    ]
            if len(owners) > 1 and project.showOwners:
                yield xhtml.td(rowspan = 4, style = 'vertical-align:top')[
                    selectionList(
                        name='owner', size=numListItems, style='width: 18ex',
                        selected=set(
                            owner or '(none)' for owner in proc.ownerFilter
                            )
                        )[
                        sorted(owner or '(none)' for owner in owners)
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

    def presentCustomBox(self, **kwargs):
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

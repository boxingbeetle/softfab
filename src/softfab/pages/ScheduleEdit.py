# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from time import localtime
from typing import Dict, Mapping, Optional

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, InitialEditArgs, InitialEditProcessor
)
from softfab.Page import PresentableError
from softfab.configlib import Config, configDB
from softfab.formlib import (
    CheckBoxesTable, DropDownList, RadioTable, checkBox, dropDownList,
    textArea, textInput
)
from softfab.pageargs import BoolArg, EnumArg, IntArg, SetArg, StrArg
from softfab.projectlib import project
from softfab.schedulelib import (
    ScheduleRepeat, Scheduled, asap, endOfTime, scheduleDB
)
from softfab.scheduleview import listToStringDays, stringToListDays, weekDays
from softfab.timelib import getTime, stringToTime
from softfab.timeview import formatTime
from softfab.webgui import (
    Column, Panel, Script, Table, addRemoveStyleScript, docLink, groupItem,
    vgroup
)
from softfab.xmlgen import XMLContent, txt, xhtml

SelectBy = Enum('SelectBy', 'NAME TAG')
'''Mechanism by which a schedule selects the configurations it will start.
'''

class ScheduleEditArgs(EditArgs):
    selectBy = EnumArg(SelectBy, SelectBy.NAME)
    configId = StrArg('')
    tag = StrArg('')
    # TODO: Make TimeArg? We already have DateArg.
    startTime = StrArg('')
    suspended = BoolArg()
    sequence = EnumArg(ScheduleRepeat, ScheduleRepeat.ONCE)
    days = SetArg()
    minDelay = IntArg(10)
    cmtrigger = StrArg('')
    comment = StrArg('')

class ScheduleEditBase(EditPage[ScheduleEditArgs, Scheduled]):
    # FabPage constants:
    icon = 'IconSchedule'
    description = 'Edit Schedule'
    linkDescription = 'New Schedule'

    # EditPage constants:
    elemTitle = 'Schedule'
    elemName = 'schedule'
    db = scheduleDB
    privDenyText = 'Job scheduling'
    useScript = False
    formId = 'schedule'
    autoName = None

    def iterStyleDefs(self):
        yield _pageStyles

    def getFormContent(self, proc):
        args = proc.args
        if args.id != '':
            yield xhtml.h2[ 'Schedule: ', xhtml.b[ args.id ]]
        yield vgroup[
            (ConfigTagTable if project.getTagKeys() else ConfigTable).instance,
            TimeTable.instance,
            SequenceTable.instance,
            _createGroupItem(args.sequence is ScheduleRepeat.WEEKLY)[
                DaysTable.instance
                ],
            _createGroupItem(args.sequence is ScheduleRepeat.CONTINUOUSLY)[
                DelayPanel.instance
                ],
            _createGroupItem(args.sequence is ScheduleRepeat.PASSIVE)[
                CMTriggerPanel.instance
                ],
            CommentPanel.instance,
            ]
        yield addRemoveStyleScript
        yield ScheduleScript.instance

_pageStyles = r'''
#jobConfTable td {
    line-height: 150%;
}
'''

class ScheduleEdit_GET(ScheduleEditBase):

    class Arguments(InitialEditArgs):
        pass

    class Processor(InitialEditProcessor[ScheduleEditArgs, Scheduled]):
        argsClass = ScheduleEditArgs

        def _initArgs(self,
                      element: Optional[Scheduled]
                      ) -> Mapping[str, object]:
            if element is None:
                return {}
            else:
                overrides = {} # type: Dict[str, object]
                configId = element['configId']
                if configId is None:
                    overrides['selectBy'] = SelectBy.TAG
                    overrides['tag'] = \
                        element['tagKey'] + ',' + element['tagValue']
                else:
                    overrides['selectBy'] = SelectBy.NAME
                    overrides['configId'] = configId
                overrides['suspended'] = element.isSuspended()
                if element['startTime'] not in (asap, endOfTime):
                    overrides['startTime'] = formatTime(element['startTime'])
                sequence = element['sequence']
                overrides['sequence'] = sequence
                if sequence is ScheduleRepeat.WEEKLY:
                    overrides['days'] = stringToListDays(element['days'])
                elif sequence is ScheduleRepeat.CONTINUOUSLY:
                    overrides['minDelay'] = element['minDelay']
                elif sequence is ScheduleRepeat.PASSIVE:
                    overrides['cmtrigger'] = '\n'.join(
                        sorted(element.getTagValues('sf.cmtrigger'))
                        )
                overrides['comment'] = element.comment
                return overrides

class ScheduleEdit_POST(ScheduleEditBase):

    class Arguments(ScheduleEditArgs):
        pass

    class Processor(EditProcessor[ScheduleEditArgs, Scheduled]):

        def _checkState(self) -> None:
            args = self.args

            if args.selectBy is SelectBy.NAME:
                configId = args.configId
                if not configId:
                    raise PresentableError(xhtml.p[
                        'Please select a configuration.'
                        ])
                if configId not in configDB:
                    raise PresentableError(xhtml.p[
                        'Configuration does not exist (anymore).'
                        ])

            if args.minDelay <= 0:
                raise PresentableError(xhtml.p[
                    'Minimal delay (%d) must be a positive integer'
                    % args.minDelay
                    ])

        def createElement(self,
                          recordId: str,
                          args: ScheduleEditArgs,
                          oldElement: Optional[Scheduled]
                          ) -> Scheduled:
            try:
                startTime = stringToTime(args.startTime)
            except ValueError:
                startTime = 0
            sequence = args.sequence
            parameters = {
                'id': recordId,
                'suspended': str(args.suspended),
                'startTime': startTime,
                'sequence': sequence.name,
                'owner': self.user.name,
                }
            if args.selectBy is SelectBy.NAME:
                parameters['configId'] = args.configId
            elif args.selectBy is SelectBy.TAG:
                key, value = args.tag.split(',')
                parameters['tagKey'] = key
                parameters['tagValue'] = value
            else:
                assert False, args.selectBy
            if sequence is ScheduleRepeat.WEEKLY:
                parameters['days'] = listToStringDays(args.days)
            elif sequence is ScheduleRepeat.CONTINUOUSLY:
                parameters['minDelay'] = args.minDelay
            element = Scheduled(parameters, args.comment, True)
            if sequence is ScheduleRepeat.PASSIVE:
                element.setTag(
                    'sf.cmtrigger',
                    ( value.strip()
                        for value in args.cmtrigger.split('\n')
                        if value.strip() )
                    )
            if oldElement is not None \
            and element.getId() == oldElement.getId():
                # Remember last started jobs.
                for jobId in oldElement.getLastJobs():
                    element._addLastJob(jobId) # pylint: disable=protected-access
                # Remember whether schedule was triggered.
                if sequence is ScheduleRepeat.PASSIVE \
                and oldElement['sequence'] is ScheduleRepeat.PASSIVE:
                    if oldElement['trigger']:
                        element.setTrigger()
            return element

class TagList(DropDownList):
    name = 'tag'
    extraAttribs = { 'style': 'width:100%' }
    def getActive(self, proc, **kwargs):
        args = proc.args
        return args.tag if args.selectBy is SelectBy.TAG else None
    def iterOptions(self, **kwargs):
        for key in project.getTagKeys():
            yield key, Config.cache.getValues(key)

def _createGroupItem(visible):
    return groupItem(class_=None if visible else 'hidden')

def _createConfigDropDownList():
    return dropDownList(name='configId', style='width:100%')[
        sorted(configDB.uniqueValues('name'))
        ]

class ConfigTable(Table):
    widgetId = 'jobConfTable'
    columns = 'Configuration',

    def iterRows(self, **kwargs):
        yield _createConfigDropDownList(),

class ConfigTagTable(RadioTable):
    name = 'selectBy'
    widgetId = 'jobConfTable'
    columns = ('Configurations', )

    def iterOptions(self, **kwargs):
        yield (
            SelectBy.NAME,
            'Configuration by name:',
            _createConfigDropDownList()
            )
        yield (
            SelectBy.TAG,
            'Configurations by tag:',
            TagList.instance
            )

    def formatOption(self, box, cells):
        label, widget = cells
        yield xhtml.label[box, ' ', label], xhtml.br, widget

class SequenceTable(RadioTable):
    name = 'sequence'
    widgetId = 'sequence'
    columns = ('Sequence', )

    def iterOptions(self, **kwargs):
        for repeat in ScheduleRepeat:
            if repeat is ScheduleRepeat.PASSIVE:
                desc = 'Passive (', docLink('/reference/api/#TriggerSchedule')[
                    'API-triggered' ], ')'
            else:
                desc = repeat.name.capitalize()
            yield repeat, desc

class TimeTable(Table):
    widgetId = 'timeTable'
    columns = 'Start Time',

    def iterRows(self, *, proc, **kwargs):
        timeStr = proc.args.startTime
        if timeStr == '':
            timeStr = formatTime(getTime())
        yield textInput(
            name='startTime', value=timeStr, style='width:100%'
            ),
        yield checkBox(name='suspended')[ 'Suspended' ],

class DaysTable(CheckBoxesTable):
    widgetId = 'daysTable'
    name = 'days'
    columns = Column('Days', cellStyle = 'nobreak'),

    def iterOptions(self, **kwargs):
        for day in weekDays:
            yield day, ( day, )

class DelayPanel(Panel):
    widgetId = 'delayPanel'
    label = 'Minimal Delay'
    content = txt('\u00A0').join((
        textInput(name='minDelay', size='4'), 'minutes'
        ))

class CMTriggerPanel(Panel):
    widgetId = 'cmTriggerPanel'
    label = 'CM Trigger Filters'

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield textArea(
            name = 'cmtrigger', cols = 40, rows = 3,
            style = 'width:100%', spellcheck = 'false'
            ).present(**kwargs)
        yield xhtml.br
        yield (
            'This sets the "', xhtml.code[ 'sf.cmtrigger' ], '" tag '
            'on this schedule, for use by a ',
            docLink('/reference/cm-triggered-build-and-test/')[
                'CM trigger script'
                ], '.'
            )

class CommentPanel(Panel):
    label = 'Optional Comment'
    content = textArea(name='comment', cols=40, rows=4, style='width:100%')

class ScheduleScript(Script):
    timeExmpl = 'YYYY-MM-DD HH:MM'

    def iterLines(self, **kwargs):
        # JavaScript thinks it's funny to start counting months at 0.
        currentTime = list(localtime(getTime()))
        currentTime[1] -= 1
        # pylint: disable=line-too-long
        # Trying to make this code fit to 80 columns is likely to cause more
        # problems than it solves.
        yield r'''
function checkStartTime() {
    var startTimeStr = document.forms.schedule.startTime.value;
    var numOfDays = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    var re = new RegExp('^\\s*((?:20)?\\d\\d)([-./])(0?[1-9]|1[0-2])\\2(0?[1-9]|[12]\\d|3[01])(?:\\s+([01]?\\d|2[0-3])[:.]([0-5]\\d))?\\s*$');
    var match = re.exec(startTimeStr);
    var invalidFormatMsg = 'Invalid date/time. \n Please use format: ''' + self.timeExmpl + '''';
    var timeInPastMsg = 'Time ' + startTimeStr + ' is in the past. Correct time automatically?';
    if (match == null) {
        alert(invalidFormatMsg);
        return false;
    }
    var year = parseInt(match[1], 10);
    var month = parseInt(match[3], 10);
    var day = parseInt(match[4], 10);
    var hour = parseInt(match[5], 10);
    var minute = parseInt(match[6], 10);
    if (RegExp) {
        if (day > 28) {
            if (day > numOfDays[month]) {
                if (((month != 2) || (day > 29)) || ( year % 4) > 0) {
                    alert(invalidFormatMsg);
                    return false;
                }
            }
        }
    }
    var startDateTime = new Date(year, (month-1), day, hour, minute);
    var currentDateTime = new Date''' + str(tuple(currentTime[ : 5])) + r''';
    if (startDateTime.getTime() < currentDateTime.getTime()) {
        return confirm(timeInPastMsg);
    }
    return true;
}
'''
        # pylint: enable=line-too-long
        yield r'''
function checkWeekDays() {
    if (document.forms.schedule.sequence[2].checked) {
        var daysSelected = false;
        for (var i = 0; i < ''' + str(len(weekDays)) + r'''; i++) {
            if (document.forms.schedule.days[i].checked) {
                daysSelected = true;
            }
        }
        if (!daysSelected) {
            alert('Please select one or more days');
            return false;
        }
    }
    return true;
}
function checkMinDelay() {
    if ((!document.forms.schedule.minDelay.value.match(/^\d+$/)) ||
        (parseInt(document.forms.schedule.minDelay.value) <= 0)) {
        if (document.forms.schedule.sequence[3].checked) {
            alert('Minimum delay must be a positive integer');
            return false;
        } else {
            document.forms.schedule.minDelay.value = '1';
        }
    }
    return true;
}
function removeTimeExmpl() {
    if (this.value == ''' + '\'' + self.timeExmpl + '''') {
        this.value = '';
    }
}
function setVisibility(node, visible) {
    if (visible) {
        removeStyle(node.parentNode, 'hidden');
    } else {
        addStyle(node.parentNode, 'hidden');
    }
}
function adjustControls() {
    setVisibility(
        document.getElementById('daysTable'),
        document.forms.schedule.sequence[2].checked
        );
    setVisibility(
        document.getElementById('delayPanel'),
        document.forms.schedule.sequence[3].checked
        );
    setVisibility(
        document.getElementById('cmTriggerPanel'),
        document.forms.schedule.sequence[4].checked
        );
}
function radio() {
    this.getElementsByTagName('input')[0].checked = true;
    adjustControls();
}
var cancelFlag = false;
function cancelClicked() {
    cancelFlag = true;
}
function checkValues() {
    if (cancelFlag) {
        cancelFlag = false;
        return true;
    } else {
        return (
            checkWeekDays() &&
            checkMinDelay() &&
            checkStartTime()
            );
    }
}
function initForm() {
    var action = document.forms.schedule.action;
    for (var i = 0; i < action.length; i++) {
        var item = action[i];
        if (item.value == 'cancel') {
            item.onclick = cancelClicked;
            break;
        }
    }
}
document.forms.schedule.startTime.onfocus = removeTimeExmpl;
document.forms.schedule.onsubmit = checkValues;
window.onload = initForm;
for (var i = 0; i < ''' + str(len(ScheduleRepeat)) + r'''; i++) {
    document.getElementById('sequence').rows[i + 1].onclick = radio;
}
'''

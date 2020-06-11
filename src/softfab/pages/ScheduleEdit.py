# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from enum import Enum
from time import localtime
from typing import (
    ClassVar, DefaultDict, Dict, Iterator, List, Mapping, Optional, Sequence,
    Tuple, cast
)

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.Page import PresentableError
from softfab.configlib import Config, ConfigDB
from softfab.formlib import (
    CheckBoxesTable, DropDownList, Option, RadioTable, checkBox, dropDownList,
    textArea, textInput
)
from softfab.pageargs import BoolArg, DictArg, EnumArg, IntArg, SetArg, StrArg
from softfab.projectlib import project
from softfab.resourcelib import ResourceDB
from softfab.restypelib import repoResourceTypeName
from softfab.schedulelib import (
    ScheduleDB, ScheduleRepeat, Scheduled, asap, endOfTime
)
from softfab.scheduleview import listToStringDays, stringToListDays, weekDays
from softfab.timelib import getTime, stringToTime
from softfab.timeview import formatTime
from softfab.userlib import UserDB
from softfab.webgui import (
    Column, Container, Panel, Script, Table, addRemoveStyleScript, docLink,
    groupItem, pageLink, vgroup
)
from softfab.xmlgen import (
    XML, XMLAttributeValue, XMLContent, XMLPresentable, xhtml
)

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
    repeat = EnumArg(ScheduleRepeat, ScheduleRepeat.ONCE)
    days = SetArg()
    minDelay = IntArg(10)
    trigger = DictArg(StrArg(), separators = '/')
    comment = StrArg('')

class ScheduleEditBase(EditPage[ScheduleEditArgs, Scheduled]):
    # FabPage constants:
    icon = 'IconSchedule'
    description = 'Edit Schedule'
    linkDescription = 'New Schedule'

    # EditPage constants:
    elemTitle = 'Schedule'
    elemName = 'schedule'
    dbName = 'scheduleDB'
    privDenyText = 'Job scheduling'
    useScript = False
    formId = 'schedule'
    autoName = None

    def iterStyleDefs(self) -> Iterator[str]:
        yield _pageStyles

    def getFormContent(self,
                       proc: EditProcessorBase[ScheduleEditArgs, Scheduled]
                       ) -> XMLContent:
        args = proc.args
        if args.id != '':
            yield xhtml.h3[ 'Schedule: ', xhtml.b[ args.id ]]
        yield vgroup[
            (ConfigTagTable if project.getTagKeys() else ConfigTable).instance,
            TimeTable.instance,
            RepeatTable.instance,
            _createGroupItem(args.repeat is ScheduleRepeat.WEEKLY)[
                DaysTable.instance
                ],
            _createGroupItem(args.repeat is ScheduleRepeat.CONTINUOUSLY)[
                DelayPanel.instance
                ],
            _createGroupItem(args.repeat is ScheduleRepeat.TRIGGERED)[
                TriggerPanel.instance
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

        configDB: ClassVar[ConfigDB]
        resourceDB: ClassVar[ResourceDB]
        scheduleDB: ClassVar[ScheduleDB]
        userDB: ClassVar[UserDB]

        def _initArgs(self,
                      element: Optional[Scheduled]
                      ) -> Mapping[str, object]:
            if element is None:
                return {}
            else:
                overrides: Dict[str, object] = {}
                configId = element.configId
                if configId is None:
                    overrides['selectBy'] = SelectBy.TAG
                    overrides['tag'] = element.tagKey + ',' + element.tagValue
                else:
                    overrides['selectBy'] = SelectBy.NAME
                    overrides['configId'] = configId
                overrides['suspended'] = element.isSuspended()
                startTime = element.startTime
                if startTime not in (asap, endOfTime):
                    overrides['startTime'] = formatTime(startTime)
                repeat = element.repeat
                overrides['repeat'] = repeat
                if repeat is ScheduleRepeat.WEEKLY:
                    overrides['days'] = stringToListDays(element.dayFlags)
                elif repeat is ScheduleRepeat.CONTINUOUSLY:
                    overrides['minDelay'] = element.minDelay
                elif repeat is ScheduleRepeat.TRIGGERED:
                    branchesByRepo: DefaultDict[str, List[str]] = \
                                    defaultdict(list)
                    for trigger in element.tags.getTagValues('sf.trigger'):
                        repoId, branch = trigger.split('/', 1)
                        branchesByRepo[repoId].append(branch)
                    overrides['trigger'] = {
                        repoId: '\n'.join(sorted(branches))
                        for repoId, branches in branchesByRepo.items()
                        }
                overrides['comment'] = element.comment
                return overrides

class ScheduleEdit_POST(ScheduleEditBase):

    class Arguments(ScheduleEditArgs):
        pass

    class Processor(EditProcessor[ScheduleEditArgs, Scheduled]):

        configDB: ClassVar[ConfigDB]
        resourceDB: ClassVar[ResourceDB]
        scheduleDB: ClassVar[ScheduleDB]

        def _checkState(self) -> None:
            args = self.args

            if args.selectBy is SelectBy.NAME:
                configId = args.configId
                if not configId:
                    raise PresentableError(xhtml.p[
                        'Please select a configuration.'
                        ])
                if configId not in self.configDB:
                    raise PresentableError(xhtml.p[
                        'Configuration does not exist (anymore).'
                        ])

            if args.minDelay <= 0:
                raise PresentableError(xhtml.p[
                    f'Minimal delay ({args.minDelay:d}) must be '
                    'a positive integer'
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
            repeat = args.repeat
            extra: Dict[str, XMLAttributeValue] = {}
            if args.selectBy is SelectBy.NAME:
                extra['configId'] = args.configId
            elif args.selectBy is SelectBy.TAG:
                key, value = args.tag.split(',')
                extra['tagKey'] = key
                extra['tagValue'] = value
            else:
                assert False, args.selectBy
            if repeat is ScheduleRepeat.WEEKLY:
                extra['days'] = listToStringDays(args.days)
            elif repeat is ScheduleRepeat.CONTINUOUSLY:
                extra['minDelay'] = args.minDelay
            element = self.scheduleDB.create(
                recordId,
                args.suspended,
                startTime,
                repeat,
                self.user.name,
                args.comment,
                extra
                )
            if repeat is ScheduleRepeat.TRIGGERED:
                triggers = cast(Mapping[str, str], args.trigger)
                tags = []
                for repoId, branchesText in triggers.items():
                    for branch in branchesText.split('\n'):
                        tags.append(f'{repoId}/{branch.strip()}')
                element.tags.setTag('sf.trigger', tags)
            if oldElement is not None \
            and element.getId() == oldElement.getId():
                # Remember last started jobs.
                for jobId in oldElement.getLastJobs():
                    element._addLastJob(jobId) # pylint: disable=protected-access
                # Remember whether schedule was triggered.
                if repeat is ScheduleRepeat.TRIGGERED \
                and oldElement.repeat is ScheduleRepeat.TRIGGERED:
                    if oldElement['trigger']:
                        element.setTrigger()
            return element

class TagList(DropDownList):
    name = 'tag'
    extraAttribs = { 'style': 'width:100%' }

    def getActive(self, **kwargs: object) -> Optional[str]:
        proc = cast(EditProcessorBase[ScheduleEditArgs, Scheduled],
                    kwargs['proc'])
        args = proc.args
        return args.tag if args.selectBy is SelectBy.TAG else None

    def iterOptions(self, **kwargs: object) -> Iterator[Option]:
        for key in project.getTagKeys():
            yield key, Config.cache.getValues(key)

def _createGroupItem(visible: bool) -> Container:
    return groupItem(class_=None if visible else 'hidden')

def _createConfigDropDownList(configDB: ConfigDB) -> XMLPresentable:
    return dropDownList(name='configId', style='width:100%')[
        sorted(configDB.uniqueValues('name'))
        ]

class ConfigTable(Table):
    widgetId = 'jobConfTable'
    columns = 'Configuration',

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        configDB: ConfigDB = getattr(kwargs['proc'], 'configDB')
        yield _createConfigDropDownList(configDB),

class ConfigTagTable(RadioTable):
    name = 'selectBy'
    widgetId = 'jobConfTable'
    columns = ('Configurations', )

    def iterOptions(self, **kwargs: object) -> Iterator[Sequence[XMLContent]]:
        configDB: ConfigDB = getattr(kwargs['proc'], 'configDB')
        yield (
            SelectBy.NAME,
            'Configuration by name:',
            _createConfigDropDownList(configDB)
            )
        yield (
            SelectBy.TAG,
            'Configurations by tag:',
            TagList.instance
            )

    def formatOption(self,
                     box: XML,
                     cells: Sequence[XMLContent]
                     ) -> XMLContent:
        label, widget = cells
        yield xhtml.label[box, ' ', label], xhtml.br, widget

class RepeatTable(RadioTable):
    name = 'repeat'
    widgetId = 'repeat'
    columns = ('Repeat', )

    def iterOptions(self, **kwargs: object) -> Iterator[Sequence[XMLContent]]:
        for repeat in ScheduleRepeat:
            if repeat is ScheduleRepeat.TRIGGERED:
                desc = 'Triggered, by API call or webhook'
            else:
                desc = repeat.name.capitalize()
            yield repeat, desc

class TimeTable(Table):
    widgetId = 'timeTable'
    columns = 'Start Time',

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(EditProcessorBase[ScheduleEditArgs, Scheduled],
                    kwargs['proc'])
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

    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[str, Sequence[XMLContent]]]:
        for day in weekDays:
            yield day, ( day, )

class DelayPanel(Panel):
    widgetId = 'delayPanel'
    label = 'Minimal Delay'
    content = xhtml['\u00A0'].join((
        textInput(name='minDelay', size='4'), 'minutes'
        ))

class TriggerPanel(Panel):
    widgetId = 'triggerPanel'
    label = 'Trigger Filters'

    def presentContent(self, **kwargs: object) -> XMLContent:
        resourceDB: ResourceDB = getattr(kwargs['proc'], 'resourceDB')
        anyRepo = False
        for repoId in sorted(resourceDB.resourcesOfType(repoResourceTypeName)):
            anyRepo = True
            yield 'Branches for repository ', xhtml.b[repoId], ':', xhtml.br
            yield textArea(
                name = f'trigger/{repoId}', cols = 40, rows = 3,
                style = 'width:100%', spellcheck = 'false'
                ).present(**kwargs)
        if anyRepo:
            yield (
                'Enter the names of branches on which commits should trigger '
                'this schedule, for example ', xhtml.code['master'], '. '
                )
        else:
            yield (
                'Please tell SoftFab about your repository by ',
                pageLink('RepoEdit')['creating a repository resource'], ', '
                'then come back here to select branches.'
                )
        yield (
            xhtml.br,
            'Read the documentation for a step-by-step description of ',
            docLink('/howto/ci/')['setting up continuous integration'],
            ' in SoftFab.'
            )

class CommentPanel(Panel):
    label = 'Optional Comment'
    content = textArea(name='comment', cols=40, rows=4, style='width:100%')

class ScheduleScript(Script):
    timeExmpl = 'YYYY-MM-DD HH:MM'

    def iterLines(self, **kwargs: object) -> Iterator[str]:
        # JavaScript thinks it's funny to start counting months at 0.
        pythonTime = localtime(getTime())
        month = pythonTime[1]
        currentTime = list(pythonTime)
        currentTime[1] = month - 1
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
    if (document.forms.schedule.repeat[2].checked) {
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
        if (document.forms.schedule.repeat[3].checked) {
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
        document.forms.schedule.repeat[2].checked
        );
    setVisibility(
        document.getElementById('delayPanel'),
        document.forms.schedule.repeat[3].checked
        );
    setVisibility(
        document.getElementById('triggerPanel'),
        document.forms.schedule.repeat[4].checked
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
    document.getElementById('repeat').rows[i + 1].onclick = radio;
}
'''

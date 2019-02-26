# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import IconModifier
from softfab.Page import (
    AccessDenied, InternalError, InvalidRequest, PresentableError, Redirect
    )
from softfab.config import mailDomain
from softfab.configlib import Config, Task, configDB
from softfab.configview import InputTable
from softfab.dialog import DialogPage, DialogProcessor, DialogStep
from softfab.formlib import (
    CheckBoxesTable, RadioTable, SingleCheckBoxTable,
    selectionList, textArea, textInput
    )
from softfab.joblib import jobDB
from softfab.pageargs import (
    ArgsCorrected, BoolArg, DictArg, EnumArg, IntArg, SetArg, StrArg
    )
from softfab.pagelinks import createJobsURL
from softfab.paramview import ParamCell, ParamOverrideTable
from softfab.productdeflib import ProductType
from softfab.projectlib import project
from softfab.selectview import TagValueEditTable, textToValues, valuesToText
from softfab.taskdeflib import taskDefDB
from softfab.taskrunnerlib import taskRunnerDB
from softfab.webgui import Table, cell
from softfab.xmlgen import xhtml

from enum import Enum


class TargetStep(DialogStep):
    name = 'target'
    title = 'Targets'

    def process(self, proc):
        if proc.args.target not in project.getTargets():
            raise ArgsCorrected(proc.args, target = min(project.getTargets()))
        return project.showTargets

    def presentFormBody(self, **kwargs):
        yield xhtml.p[ 'Select target to test:' ]
        yield TargetTable.instance.present(**kwargs)

    def verify(self, proc):
        return TaskStep

class TaskStep(DialogStep):
    name = 'task'
    title = 'Tasks'

    def process(self, proc):
        # TODO: Maybe check privileges for individual steps at the page level?
        #       It would be a bit strange to be stopped halfway a wizard.
        proc.req.checkPrivilege('td/l', 'access task list')
        return True

    def presentFormBody(self, **kwargs):
        yield xhtml.p[ 'Select task(s) to execute:' ]
        yield TaskTable.instance.present(**kwargs)
        if project['trselect']:
            yield ShowTaskRunnerSelectionTable.instance.present(**kwargs)

    def verify(self, proc):
        tasks = proc.args.tasks
        if len(tasks) == 0:
            raise PresentableError(
                'Please select one or more tasks.'
                )

        # Keep the priorities dictionary small.
        # This is essential to get decent performance on projects with
        # a large number of task definitions.
        priorities = proc.args.prio
        filteredPrio = {}
        for task in tasks:
            prio = priorities.get(task, 0)
            if prio != 0:
                filteredPrio[task] = prio
        if filteredPrio != priorities:
            raise ArgsCorrected(proc.args, prio = filteredPrio)

        return RunnerStep

class RunnerStep(DialogStep):
    name = 'runner'
    title = 'Task Runners'

    def process(self, proc):
        if not proc.args.trselect:
            return False
        elif project['trselect']:
            return len(taskRunnerDB) > 0
        elif proc.args.runners or proc.args.pertask:
            raise ArgsCorrected(proc.args, runners = set(), pertask = False)
        else:
            return False

    def presentFormBody(self, **kwargs):
        yield xhtml.p[ 'Select Task Runner(s) to use:' ]
        yield xhtml.p(class_ = 'hint')[
            '(Nothing selected means any Task Runners can'
            ' be used, including those not in this list)'
            ]
        yield TaskRunnerSelectionTable.instance.present(**kwargs)
        yield TaskRunnersPerTaskTable.instance.present(**kwargs)

    def verify(self, proc):
        if proc.args.runners:
            taskRunnerCaps = [
                runner.capabilities
                for runner in (
                    taskRunnerDB.get(runnerId)
                    for runnerId in proc.args.runners
                    )
                if runner is not None
                ]
            if not all(
                any(caps.issubset(trCaps) for trCaps in taskRunnerCaps)
                for caps in (task.getNeededCaps() for task in proc.iterTasks())
                ):
                raise PresentableError(
                    'The selected Task Runners are not sufficient '
                    'to execute this job.'
                    )
        return RunnerPerTaskStep

class RunnerPerTaskStep(DialogStep):
    name = 'runnerpt'
    title = 'Task Runners'

    def process(self, proc):
        return proc.args.pertask and len(proc.args.tasks) > 0

    def presentFormBody(self, proc, **kwargs):
        proc.config = proc.getConfig()
        proc.taskRunners = sorted(
            runner for runner in taskRunnerDB
            if runner['target'] == proc.args.target
            )

        yield xhtml.p[ 'Select Task Runner(s) to use per task:' ]
        yield xhtml.p(class_ = 'hint')[
            '(Nothing selected means default settings for the job are used)'
            ]
        yield TaskRunnersTable.instance.present(proc=proc, **kwargs)

    def verify(self, proc):
        return ParamStep

class ParamStep(DialogStep):
    name = 'param'
    title = 'Parameters'

    def process(self, proc):
        return (
                # Task Runner should be selected per task.
                proc.args.pertask and len(proc.args.tasks) > 0
            ) or any(
                # Inputs should be selected.
                inp.isLocal() or inp.getType() is not ProductType.TOKEN
                for inp in proc.getConfig().getInputs()
            ) or any(
                # Parameters should be provided.
                not all(
                    task.isFinal(param) or param in ParamTable.suppressedParams
                    for param in task.getParameters()
                    )
                for task in (
                    taskDefDB[task] for task in proc.args.tasks
                    )
            )

    def presentFormBody(self, proc, **kwargs):
        # No need to check for tasks here, because if there were no tasks
        # then process() would have skipped this step right to 'action'.

        yield xhtml.p[ 'Provide input values:' ]

        # Construct Config object, because it has useful query methods.
        config = proc.getConfig()
        # Input products:
        yield ConfigInputTable.instance.present(
            proc=proc, taskSet=config, **kwargs
            )
        # Task parameters:
        proc.tasks = [
            ( taskId, taskDefDB[taskId],
              config.getTask(taskId).getParameters() )
            for taskId in proc.args.tasks
            ]
        yield ParamTable.instance.present(proc=proc, **kwargs)

    def verify(self, proc):
        return ActionStep

Actions = Enum('Actions', 'START TAGS')

class ActionStep(DialogStep):
    name = 'action'
    title = 'Action'

    def presentFormBody(self, **kwargs):
        # TODO: Early instantiation has to be forced to make sure the controls
        #       in the table are first in line for receiving focus. This is not
        #       intuitive at all.
        yield ActionTable.instance.present(**kwargs)
        yield xhtml.p[
            'Job configuration name: ',
            textInput(name = 'config', size = 36).present(**kwargs)
            ]
        yield xhtml.p[
            'Job description:',
            xhtml.br,
            textArea(name = 'comment', cols = 60, rows = 3).present(**kwargs)
            ]
        yield NotifyTable.instance.present(**kwargs)
        yield xhtml.p[
            'Enter email addresses / prefixes: ',
            xhtml.br,
            textArea(
                name = 'notify', cols = 60, rows = 4, spellcheck = 'false'
                ).present(**kwargs),
            xhtml.br,
            'It is possible to enter a prefix if the mail domain is: @',
            mailDomain, xhtml.br,
            'Multiple email addresses and prefixes can be entered, ',
            'separated by commas.'
            ]

    def verify(self, proc):
        action = proc.args.action
        if action is Actions.START:
            if not proc.getConfig().hasValidInputs():
                raise PresentableError(
                    'Please specify "Local at" for all local inputs.'
                    )
            multiMax = project['maxjobs']
            if proc.args.multi < 0:
                raise PresentableError(
                    'A negative multiple jobs count is not possible.'
                    )
            if proc.args.multi > multiMax:
                raise PresentableError((
                    'Multiple jobs limit (%d) exceeded.' % multiMax,
                    xhtml.br,
                    'If you want to have a higher multiple jobs limit, '
                    'please ask your SoftFab operator to  increase it. See ',
                    xhtml.a(href = 'ProjectEdit')[ 'Configure / Project' ], '.'
                    ))
            return StartStep
        elif action is Actions.TAGS:
            try:
                configDB.checkId(proc.args.config)
            except KeyError as ex:
                raise PresentableError(ex.args[0])
            return TagsStep
        else:
            raise InternalError('Unknown action "%s"' % action)

class StartStep(DialogStep):
    name = 'start'
    title = 'Started'

    def process(self, proc):
        proc.req.checkPrivilege('j/c', 'create jobs')
        if len(proc.args.tasks) == 0:
            # Normally this will be stopped by TaskStep.verify(), but it is
            # not safe to rely on that because the request might be mangled
            # by the browser (this has happened, see bug 297).
            # In the new design, all previous steps are traversed for each
            # processing, but we rely on info from the request to know which
            # step to start from, so this extra check is still useful.
            raise InvalidRequest('No tasks selected')
        config = proc.getConfig()
        jobIds = []
        for _ in range(proc.args.multi):
            job = config.createJob(proc.req.getUserName())
            jobDB.add(job)
            jobIds.append(job.getId())
        raise Redirect(createJobsURL(jobIds))

    def verify(self, proc):
        # Unreachable because process() never returns normally.
        assert False

# TODO: Here we present the tags as part of the configuration, while changing
#       the tags can be done separately from changing the configuration.
#       What looks strange in particular is that the overwrite confirmation
#       happens after the tagging, while the naming happens before.
class TagsStep(DialogStep):
    name = 'tags'
    title = 'Tags'

    def process(self, proc):
        return bool(project.getTagKeys())

    def presentFormBody(self, proc, **kwargs):
        yield xhtml.p[ 'Selection tags:' ]
        tags = dict(
            ( key, proc.args.tagvalues.get(index, '') )
            for index, key in proc.args.tagkeys.items()
            )
        proc.getValues = lambda key: tags.get(key, '')
        yield ConfigTagValueEditTable.instance.present(proc=proc, **kwargs)

    def verify(self, proc):
        return ConfirmStep

class ConfigTagValueEditTable(TagValueEditTable):
    tagCache = Config.cache

class ConfirmStep(DialogStep):
    name = 'confirm'
    title = 'Save'

    def process(self, proc):
        show = proc.args.config in configDB
        if show:
            proc.nextLabel = 'OK'
        return show

    def presentFormBody(self, proc, **kwargs):
        yield xhtml.p[ 'A configuration named ', xhtml.b[ proc.args.config ],
            ' already exists.' ]
        yield xhtml.p[ 'Do you want to ', xhtml.b[ 'overwrite' ], ' it?' ]

    def verify(self, proc):
        return SaveStep

class SaveStep(DialogStep):
    name = 'save'
    title = 'Saved'

    def process(self, proc):
        config = proc.getConfig()
        oldConfig = configDB.get(config.getId())
        if oldConfig is None:
            proc.req.checkPrivilege('c/c', 'create configurations')
            configDB.add(config)
        else:
            proc.req.checkPrivilegeForOwned(
                'c/m', oldConfig,
                ( 'modify configurations owned by other users',
                  'modify configurations' )
                )
            configDB.update(config)
        return True

    def presentContent(self, proc):
        yield (
            xhtml.p[ 'Configuration saved.' ],
            self.backToParent(proc.req)
            )
        # TODO: Having a direct way to execute the saved config would be useful.

    def verify(self, proc):
        # Unreachable with valid input because process() always returns True
        # and presentContent() does not render the form.
        raise InvalidRequest('Attempt to skip the "save" step')

EntranceSteps = Enum('EntranceSteps', 'EDIT')
'''Names of steps that can be jumped to by other pages.
'''

class Execute(DialogPage):
    icon = 'IconExec'
    iconModifier = IconModifier.EDIT
    description = 'Execute'
    linkDescription = 'Execute from Scratch'
    steps = (
        TargetStep, TaskStep, RunnerStep, RunnerPerTaskStep, ParamStep,
        ActionStep, StartStep, TagsStep, ConfirmStep, SaveStep,
        )

    class Arguments(DialogPage.Arguments):
        target = StrArg('')
        tasks = SetArg()
        prio = DictArg(IntArg())
        prod = DictArg(StrArg())
        multi = IntArg(1)
        notify = StrArg('')
        onfail = StrArg('always')
        comment = StrArg('')
        config = StrArg('')
        local = DictArg(StrArg())
        values = DictArg(StrArg())
        poverride = DictArg(BoolArg())
        tagkeys = DictArg(StrArg())
        tagvalues = DictArg(StrArg())
        trselect = BoolArg()
        runners = SetArg()
        pertask = BoolArg()
        runnerspt = DictArg(SetArg())
        lref = DictArg(StrArg()) # See configview.InputTable
        action = EnumArg(Actions, Actions.START)
        step = EnumArg(EntranceSteps, None)

        def load(self, req):
            try:
                config = configDB[self.config]
            except KeyError:
                raise InvalidRequest(
                    'Configuration "%s" does not exist' % self.config
                    )

            req.checkPrivilege('c/a', 'access configurations')
            tasks = config.getTasks()

            values = {}
            poverride = {}
            runnerspt = {}
            for task in tasks:
                taskDef = taskDefDB[task['name']]
                for param in taskDef.getParameters().keys():
                    paramKey = task['name'] + '/' + param
                    value = task.getParameter(param)
                    values[paramKey] = value or ''
                    poverride[paramKey] = value is not None
                runners = task.getRunners()
                if runners:
                    runnerspt[task['name']] = set(runners)

            onfail = 'always'    # default setting
            notify = config.getParameter('notify') or ''
            parts = notify.split(':', 1)
            if len(parts) == 2 and parts[0] == 'mailto':
                notify = parts[1]
                if config.getParameter('notify-mode') == 'onfail':
                    onfail = 'onfail'
                elif config.getParameter('notify-mode') == 'onerror':
                    onfail = 'onerror'

            tagkeys = {}
            tagvalues = {}
            for index, key in enumerate(config.getTagKeys()):
                indexStr = str(index)
                tagkeys[indexStr] = key
                tagvalues[indexStr] = valuesToText(config.getTagValues(key))

            return self.__class__(
                config = config.getId(),
                target = config['target'],
                tasks = frozenset(
                    task['name']
                    for task in tasks
                    ),
                prio = dict(
                    ( task['name'], task['priority'] )
                    for task in tasks
                    ),
                prod = dict(
                    ( prod['name'], prod.get('locator') or '' )
                    for prod in config.getInputs()
                    ),
                local = dict(
                    ( prod['name'], prod['localAt'] )
                    for prod in config.getInputs()
                    if prod.get('localAt') is not None
                    ),
                values = values,
                poverride = poverride,
                runnerspt = runnerspt,
                comment = config.comment,
                trselect = config['trselect'],
                pertask = bool(runnerspt),
                runners = set(config.getRunners()),
                notify = notify,
                onfail = onfail,
                tagkeys = tagkeys,
                tagvalues = tagvalues,
                )

    class Processor(DialogProcessor):
        __config = None

        def iterTasks(self):
            args = self.args
            for taskId in args.tasks:
                taskDef = taskDefDB[taskId]
                taskParams = {}
                for name, defValue in taskDef.getParameters().items():
                    paramKey = taskId + '/' + name
                    value = args.values.get(paramKey)
                    if args.poverride.get(paramKey, False):
                        if value is None:
                            value = defValue
                        if value is not None:
                            taskParams[name] = value
                yield Task.create(
                    name = taskId,
                    priority = int(args.prio.get(taskId, 0)),
                    parameters = taskParams,
                    )

        def getConfig(self):
            if self.__config is None:
                args = self.args

                jobParams = {}
                if args.notify:
                    jobParams['notify'] = 'mailto:' + args.notify
                    if args.onfail:
                        jobParams['notify-mode'] = args.onfail

                config = Config.create(
                    name = args.config,
                    target = args.target,
                    owner = self.req.getUserName(),
                    trselect = args.trselect,
                    comment = args.comment,
                    jobParams = jobParams,
                    tasks = self.iterTasks(),
                    runners = args.runners,
                    )

                for group, inputs in config.getInputsGrouped():
                    localAt = None
                    if group is not None:
                        # Local products.
                        for inp in inputs:
                            localAt = args.local.get(inp['name'])
                            if localAt == '':
                                # Browsers that support the 'required'
                                # attribute won't allow form submissions
                                # without filling in the location, but
                                # we handle this just in case.
                                localAt = None
                            elif localAt is not None:
                                break
                    for inp in inputs:
                        if inp.getType() is ProductType.TOKEN:
                            locator = 'token'
                        else:
                            locator = args.prod.get(inp['name'])
                        if locator is not None:
                            inp.setLocator(locator, localAt)

                if args.pertask:
                    for item in config.getTaskGroupSequence():
                        tasks = item.getTaskSequence() if item.isGroup() \
                            else ( item, )
                        runners = args.runnerspt.get(
                            tasks[0].getName(), frozenset()
                            )
                        for task in tasks:
                            # pylint: disable=protected-access
                            task._setRunners(runners)

                for index, key in args.tagkeys.items():
                    config.setTag(key, textToValues(
                        args.tagvalues.get(index, '')
                        ))

                self.__config = config
            return self.__config

        def argsChanged(self):
            self.__config = None

        def getInitial(self, req):
            if req.args.step is EntranceSteps.EDIT:
                return TargetStep, req.args.load(req)
            elif req.args.config != '':
                return RunnerStep, req.args.load(req)
            else:
                return TargetStep, Execute.Arguments()

    def checkAccess(self, req):
        if not (req.hasPrivilege('c/a') or req.hasPrivilege('j/c')):
            raise AccessDenied()

class TargetTable(RadioTable):
    name = 'target'
    columns = ('Target', )

    def iterOptions(self, **kwargs):
        for target in sorted(project.getTargets()):
            yield target, ( target, '\u00A0' )


class NotifyTable(RadioTable):
    name = 'onfail'
    columns = ('Notify by email when job has finished', )

    def iterOptions(self, **kwargs):
        yield 'always', ( 'always', '\u00A0' )
        yield 'onfail', ( 'only if a task result is a warning or an error',
            '\u00A0' )
        yield 'onerror', ( 'only if a task result is an error', '\u00A0' )


class TaskTable(CheckBoxesTable):
    name = 'tasks'

    def iterColumns(self, **kwargs):
        yield 'Task ID'
        yield 'Title'
        if project['taskprio']:
            yield 'Priority'

    def iterOptions(self, proc, **kwargs):
        # Create separate lists for selected and unselected tasks.
        selectedTaskIds = []
        unselectedTaskIds = []
        for taskId in sorted(taskDefDB.keys()):
            if taskId in proc.args.tasks:
                selectedTaskIds.append(taskId)
            else:
                unselectedTaskIds.append(taskId)

        # Yield options.
        for taskIds, disabled in (
                (selectedTaskIds, False),
                (unselectedTaskIds, True)
                ):
            for taskId in taskIds:
                task = taskDefDB[taskId]
                cells = [ taskId, task.getTitle() ]
                if project['taskprio']:
                    cells.append(
                        textInput(
                            name = 'prio.' + taskId,
                            value = str(proc.args.prio.get(taskId, 0)),
                            size = 5, maxlength = 6,
                            disabled = disabled,
                            ).present(proc=proc, **kwargs)
                        )
                yield taskId, cells

    def getActive(self, proc, **kwargs):
        return proc.args.tasks

class ShowTaskRunnerSelectionTable(SingleCheckBoxTable):
    name = 'trselect'
    label = 'Show Task Runner selection page'

class TaskRunnerSelectionTable(CheckBoxesTable):
    name = 'runners'
    columns = 'Task Runner',

    def iterOptions(self, proc, **kwargs):
        taskCapsList = []
        requiredCaps = None
        for task in proc.iterTasks():
            caps = task.getNeededCaps()
            taskCapsList.append(caps)
            if requiredCaps is None:
                requiredCaps = set(caps)
            else:
                requiredCaps &= caps
        taskCapsList.sort(key=len)

        taskRunners = (
            runner for runner in taskRunnerDB
            if runner['target'] == proc.args.target
            )
        # Are there tasks with non-empty required capability set?
        if len(taskCapsList[0]) > 0:
            def capsMatch(runner):
                trCaps = runner.capabilities
                if not requiredCaps.issubset(trCaps):
                    return False
                trCapsLen = len(trCaps)
                for caps in taskCapsList:
                    if len(caps) > trCapsLen:
                        return False
                    elif caps.issubset(trCaps):
                        return True
                return False
            taskRunners = tuple(
                runner for runner in taskRunners if capsMatch(runner)
                )

        for runnerId in sorted(runner.getId() for runner in taskRunners):
            yield runnerId, ( runnerId, )

    def getActive(self, proc, **kwargs):
        return proc.args.runners

class TaskRunnersPerTaskTable(SingleCheckBoxTable):
    name = 'pertask'
    label = 'Specify Task Runners per task'

class ConfigInputTable(InputTable):

    def filterTaskRunner(self, taskRunner, taskSet, group, inp):
        return taskRunner['target'] == taskSet['target'] and (
            group is None or group.canRunOn(taskRunner.getId())
            )

class ParamTable(ParamOverrideTable):

    def getParamCell(self, proc, taskId, name, curValue, defValue):
        return ParamCell(
            taskId + '/' + name, curValue or '', defValue
            )

class TaskRunnersTable(Table):
    columns = 'Task', 'Task Runners'

    def iterRows(self, proc, **kwargs):
        runnerspt = proc.args.runnerspt
        config = proc.config
        taskRunners = proc.taskRunners
        for item in config.getTaskGroupSequence():
            caps = item.getNeededCaps()
            tasks = item.getTaskSequence() if item.isGroup() else ( item, )
            runners = [
                runner.getId() for runner in taskRunners
                if caps.issubset(runner.capabilities)
                ]
            taskName = tasks[0].getName()
            listBox = selectionList(
                name='runnerspt.' + taskName,
                selected=runnerspt.get(taskName, frozenset()),
                size=max(min(len(runners), 4), len(tasks)),
                style='width:100%;'
                )[ runners ]
            yield taskName, cell(rowspan = len(tasks))[listBox]
            for task in tasks[1 : ]:
                yield task.getName(),

class ActionTable(RadioTable):
    name = 'action'
    columns = ('Execute now or Save', )

    def iterOptions(self, **kwargs):
        # The onchange event handlers are there to make sure the right
        # radio button is activated when text is pasted into an edit
        # box from the context menu (right mouse button).
        yield Actions.START, 'Execute now', (
            ', ',
            textInput(
                name = 'multi', size = 3,
                onchange = "form['%s'][0].checked=true" % self.name
                ).present(**kwargs),
            ' times (configuration will not be saved).'
            )
        yield Actions.TAGS, 'Save configuration', None

    def formatOption(self, box, cells):
        label, rest = cells
        yield xhtml.label[box, ' ', label] + rest

# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import (
    AbstractSet, ClassVar, Dict, Iterable, Iterator, List, Mapping, Optional,
    Sequence, Tuple, Type, cast
)

from softfab.FabPage import IconModifier
from softfab.Page import InternalError, InvalidRequest, PageProcessor, Redirect
from softfab.compat import NoReturn
from softfab.configlib import Config, ConfigDB, Input, Task, TaskSetWithInputs
from softfab.configview import InputTable
from softfab.dialog import (
    ContinuedDialogProcessor, DialogPage, DialogStep, InitialDialogProcessor,
    VerificationError
)
from softfab.formlib import (
    CheckBoxesTable, RadioTable, SingleCheckBoxTable, selectionList, textArea,
    textInput
)
from softfab.joblib import JobDB
from softfab.pageargs import (
    ArgsCorrected, BoolArg, DictArg, DictArgInstance, EnumArg, IntArg,
    PageArgs, SetArg, StrArg
)
from softfab.pagelinks import createJobsURL
from softfab.paramview import ParamCell, ParamOverrideTable
from softfab.productdeflib import ProductType
from softfab.projectlib import project
from softfab.resourcelib import TaskRunner, getTaskRunner, iterTaskRunners
from softfab.selectview import TagValueEditTable, textToValues, valuesToText
from softfab.taskdeflib import TaskDefDB
from softfab.taskgroup import LocalGroup, TaskGroup
from softfab.userlib import (
    AccessDenied, User, checkPrivilege, checkPrivilegeForOwned
)
from softfab.webgui import Column, Table, cell
from softfab.xmlgen import XML, XMLContent, xhtml


class TargetStep(DialogStep):
    name = 'target'
    title = 'Targets'

    def process(self, proc: 'Execute_POST.Processor') -> bool:
        projectTargets = project.getTargets()
        if projectTargets:
            return True
        else:
            if proc.args.target:
                raise ArgsCorrected(proc.args, target=())
            else:
                return False

    def presentFormBody(self, **kwargs: object) -> XMLContent:
        yield xhtml.p[ 'Select target to test:' ]
        yield TargetTable.instance.present(**kwargs)
        yield xhtml.p[
            'Selecting no targets will produce a single target-less job.'
            ]

    def verify(self, proc: 'Execute_POST.Processor') -> Type[DialogStep]:
        return TaskStep

class TaskStep(DialogStep):
    name = 'task'
    title = 'Tasks'

    def process(self, proc: 'Execute_POST.Processor') -> bool:
        # TODO: Maybe check privileges for individual steps at the page level?
        #       It would be a bit strange to be stopped halfway a wizard.
        checkPrivilege(proc.user, 'td/l', 'access task list')
        return True

    def presentFormBody(self, **kwargs: object) -> XMLContent:
        yield xhtml.p[ 'Select task(s) to execute:' ]
        yield TaskTable.instance.present(**kwargs)
        yield ShowTaskRunnerSelectionTable.instance.present(**kwargs)

    def verify(self, proc: 'Execute_POST.Processor') -> Type[DialogStep]:
        tasks = proc.args.tasks
        if len(tasks) == 0:
            raise VerificationError(
                'Please select one or more tasks.'
                )

        # Keep the priorities dictionary small.
        # This is essential to get decent performance on projects with
        # a large number of task definitions.
        priorities = cast(DictArgInstance[int], proc.args.prio)
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

    def process(self, proc: 'Execute_POST.Processor') -> bool:
        return proc.args.trselect and any(iterTaskRunners())

    def presentFormBody(self, **kwargs: object) -> XMLContent:
        yield xhtml.p[ 'Select Task Runner(s) to use:' ]
        yield xhtml.p(class_ = 'hint')[
            '(Nothing selected means any Task Runners can'
            ' be used, including those not in this list)'
            ]
        yield TaskRunnerSelectionTable.instance.present(**kwargs)
        yield TaskRunnersPerTaskTable.instance.present(**kwargs)

    def verify(self, proc: 'Execute_POST.Processor') -> Type[DialogStep]:
        if proc.args.runners:
            taskRunnerCaps = []
            for runnerId in proc.args.runners:
                try:
                    runner = getTaskRunner(runnerId)
                except KeyError:
                    pass
                else:
                    taskRunnerCaps.append(runner.capabilities)
            if not all(
                any(caps <= trCaps for trCaps in taskRunnerCaps)
                for caps in (task.getNeededCaps() for task in proc.iterTasks())
                ):
                raise VerificationError(
                    'The selected Task Runners are not sufficient '
                    'to execute this job.'
                    )
        return RunnerPerTaskStep

class RunnerPerTaskStep(DialogStep):
    name = 'runnerpt'
    title = 'Task Runners'

    def process(self, proc: 'Execute_POST.Processor') -> bool:
        return proc.args.pertask and len(proc.args.tasks) > 0

    def presentFormBody(self, **kwargs: object) -> XMLContent:
        proc = cast(Execute_POST.Processor, kwargs['proc'])
        yield xhtml.p[ 'Select Task Runner(s) to use per task:' ]
        yield xhtml.p(class_ = 'hint')[
            '(Nothing selected means default settings for the job are used)'
            ]
        yield TaskRunnersTable.instance.present(
            config=proc.getConfig(),
            taskRunners=sorted(proc.iterTaskRunners()),
            runnersPerTask=proc.args.runnerspt,
            **kwargs
            )

    def verify(self, proc: 'Execute_POST.Processor') -> Type[DialogStep]:
        return ParamStep

class ParamStep(DialogStep):
    name = 'param'
    title = 'Parameters'

    def process(self, proc: 'Execute_POST.Processor') -> bool:
        taskDefDB = proc.taskDefDB
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

    def presentFormBody(self, **kwargs: object) -> XMLContent:
        proc = cast(Execute_POST.Processor, kwargs['proc'])

        # No need to check for tasks here, because if there were no tasks
        # then process() would have skipped this step right to 'action'.

        yield xhtml.p[ 'Provide input values:' ]

        # Construct Config object, because it has useful query methods.
        config = proc.getConfig()
        # Input products:
        yield ConfigInputTable.instance.present(taskSet=config, **kwargs)
        # Task parameters:
        taskDefDB = proc.taskDefDB
        tasks = [
            ( taskId, taskDefDB[taskId],
              cast(Task, config.getTask(taskId)).getParameters() )
            for taskId in proc.args.tasks
            ]
        yield ParamTable.instance.present(tasks=tasks, **kwargs)

    def verify(self, proc: 'Execute_POST.Processor') -> Type[DialogStep]:
        return ActionStep

Actions = Enum('Actions', 'START TAGS')

class ActionStep(DialogStep):
    name = 'action'
    title = 'Action'

    def presentFormBody(self, **kwargs: object) -> XMLContent:
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
            'Enter email addresses: ',
            xhtml.br,
            textArea(
                name = 'notify', cols = 60, rows = 4, spellcheck = 'false'
                ).present(**kwargs),
            xhtml.br,
            'Multiple email addresses can be entered, ',
            'separated by commas, semicolons and/or whitespace.'
            ]

    def verify(self, proc: 'Execute_POST.Processor') -> Type[DialogStep]:
        action = proc.args.action
        if action is Actions.START:
            if not proc.getConfig().hasValidInputs():
                raise VerificationError(
                    'Please specify "Local at" for all local inputs.'
                    )
            multiMax = cast(int, project['maxjobs'])
            if proc.args.multi < 0:
                raise VerificationError(
                    'A negative multiple jobs count is not possible.'
                    )
            if proc.args.multi > multiMax:
                raise VerificationError((
                    f'Multiple jobs limit ({multiMax:d}) exceeded.',
                    xhtml.br,
                    'If you want to have a higher multiple jobs limit, '
                    'please ask your SoftFab operator to  increase it. See ',
                    xhtml.a(href = 'ProjectEdit')[ 'Configure / Project' ], '.'
                    ))
            return StartStep
        elif action is Actions.TAGS:
            try:
                proc.configDB.checkId(proc.args.config)
            except KeyError as ex:
                raise VerificationError(ex.args[0])
            return TagsStep
        else:
            raise InternalError(f'Unknown action "{action}"')

class StartStep(DialogStep):
    name = 'start'
    title = 'Started'

    def process(self, proc: 'Execute_POST.Processor') -> bool:
        checkPrivilege(proc.user, 'j/c', 'create jobs')
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
            for job in config.createJobs(proc.user.name):
                proc.jobDB.add(job)
                jobIds.append(job.getId())
        raise Redirect(createJobsURL(jobIds))

    def verify(self, proc: 'Execute_POST.Processor') -> NoReturn:
        # Unreachable because process() never returns normally.
        assert False

# TODO: Here we present the tags as part of the configuration, while changing
#       the tags can be done separately from changing the configuration.
#       What looks strange in particular is that the overwrite confirmation
#       happens after the tagging, while the naming happens before.
class TagsStep(DialogStep):
    name = 'tags'
    title = 'Tags'

    def process(self, proc: 'Execute_POST.Processor') -> bool:
        return bool(project.getTagKeys())

    def presentFormBody(self, **kwargs: object) -> XMLContent:
        proc = cast(Execute_POST.Processor, kwargs['proc'])
        tagkeys = cast(DictArgInstance[str], proc.args.tagkeys)
        tagvalues = cast(DictArgInstance[str], proc.args.tagvalues)
        yield xhtml.p[ 'Selection tags:' ]
        tags = {key: tagvalues.get(index, '') for index, key in tagkeys.items()}
        yield ConfigTagValueEditTable.instance.present(
            getValues=lambda key: tags.get(key, ''),
            **kwargs
            )

    def verify(self, proc: 'Execute_POST.Processor') -> Type[DialogStep]:
        return ConfirmStep

class ConfigTagValueEditTable(TagValueEditTable):
    tagCache = Config.cache

class ConfirmStep(DialogStep):
    name = 'confirm'
    title = 'Save'

    def process(self, proc: 'Execute_POST.Processor') -> bool:
        show = proc.args.config in proc.configDB
        if show:
            proc.nextLabel = 'OK'
        return show

    def presentFormBody(self, **kwargs: object) -> XMLContent:
        proc = cast(Execute_POST.Processor, kwargs['proc'])
        yield xhtml.p[ 'A configuration named ', xhtml.b[ proc.args.config ],
            ' already exists.' ]
        yield xhtml.p[ 'Do you want to ', xhtml.b[ 'overwrite' ], ' it?' ]

    def verify(self, proc: 'Execute_POST.Processor') -> Type[DialogStep]:
        return SaveStep

class SaveStep(DialogStep):
    name = 'save'
    title = 'Saved'

    def process(self, proc: 'Execute_POST.Processor') -> bool:
        config = proc.getConfig()
        configDB = proc.configDB
        oldConfig = configDB.get(config.getId())
        if oldConfig is None:
            checkPrivilege(proc.user, 'c/c', 'create configurations')
            configDB.add(config)
        else:
            checkPrivilegeForOwned(
                proc.user, 'c/m', oldConfig,
                ( 'modify configurations owned by other users',
                  'modify configurations' )
                )
            configDB.update(config)
        return True

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(PageProcessor, kwargs['proc'])
        yield xhtml.p[ 'Configuration saved.' ]
        yield self._page.backToParent(proc.args)
        # TODO: Having a direct way to execute the saved config would be useful.

    def verify(self, proc: 'Execute_POST.Processor') -> Type[DialogStep]:
        # Unreachable with valid input because process() always returns True
        # and presentContent() does not render the form.
        raise InvalidRequest('Attempt to skip the "save" step')

EntranceSteps = Enum('EntranceSteps', 'EDIT')
'''Names of steps that can be jumped to by other pages.
'''

class ExecuteProcessorMixin:

    configDB: ClassVar[ConfigDB]
    taskDefDB: ClassVar[TaskDefDB]

    __config: Optional[Config] = None
    user: User

    def iterTasks(self) -> Iterator[Task]:
        args = cast(Execute_POST.Arguments, getattr(self, 'args'))
        values = cast(Mapping[str, str], args.values)
        poverride = cast(Mapping[str, bool], args.poverride)
        prio = cast(Mapping[str, int], args.prio)
        taskDefDB = self.taskDefDB
        for taskId in args.tasks:
            taskDef = taskDefDB[taskId]
            taskParams = {}
            for name, defValue in taskDef.getParameters().items():
                paramKey = taskId + '/' + name
                value = values.get(paramKey)
                if poverride.get(paramKey, False):
                    if value is None:
                        value = defValue
                    if value is not None:
                        taskParams[name] = value
            yield Task.create(
                name = taskId,
                priority = prio.get(taskId, 0),
                parameters = taskParams,
                )

    def iterTaskRunners(self) -> Iterator[TaskRunner]:
        """Iterate through the Task Runners that match our targets.
        """
        args = cast(Execute_POST.Arguments, getattr(self, 'args'))
        targets = args.target
        if targets:
            for runner in iterTaskRunners():
                if runner.targets & targets:
                    yield runner
        else:
            yield from iterTaskRunners()

    def getConfig(self) -> Config:
        if self.__config is None:
            args = cast(Execute_POST.Arguments, getattr(self, 'args'))
            local = cast(Mapping[str, str], args.local)
            prod = cast(Mapping[str, str], args.prod)
            tagkeys = cast(Mapping[str, str], args.tagkeys)
            tagvalues = cast(Mapping[str, str], args.tagvalues)

            jobParams: Dict[str, str] = {}
            if args.notify:
                jobParams['notify'] = 'mailto:' + args.notify
                if args.onfail:
                    jobParams['notify-mode'] = args.onfail

            config = Config.create(
                name = args.config,
                targets = args.target,
                owner = self.user.name,
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
                        localAt = local.get(inp.getName())
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
                        locator: Optional[str] = 'token'
                    else:
                        locator = prod.get(inp.getName())
                    if locator is not None:
                        inp.setLocator(locator, localAt)

            if args.pertask:
                runnerspt = cast(Mapping[str, AbstractSet[str]], args.runnerspt)
                for item in config.getTaskGroupSequence():
                    if isinstance(item, TaskGroup):
                        tasks = item.getTaskSequence()
                    else:
                        tasks = (item,)
                    runners = runnerspt.get(
                        tasks[0].getName(), frozenset()
                        )
                    for task in tasks:
                        # pylint: disable=protected-access
                        task._setRunners(runners)

            for index, key in tagkeys.items():
                config.setTag(key, textToValues(tagvalues.get(index, '')))

            self.__config = config
        return self.__config

    def argsChanged(self) -> None:
        self.__config = None

class ExecuteBase(DialogPage):
    icon = 'IconExec'
    iconModifier = IconModifier.EDIT
    description = 'Execute'

    steps = (
        TargetStep, TaskStep, RunnerStep, RunnerPerTaskStep, ParamStep,
        ActionStep, StartStep, TagsStep, ConfirmStep, SaveStep,
        )

    def checkAccess(self, user: User) -> None:
        if not (user.hasPrivilege('c/a') or user.hasPrivilege('j/c')):
            raise AccessDenied()

class Execute_GET(ExecuteBase, DialogPage):
    linkDescription = 'Execute from Scratch'

    class Arguments(DialogPage.Arguments):
        config = StrArg('')
        step = EnumArg(EntranceSteps, None)

    class Processor(ExecuteProcessorMixin,
                    InitialDialogProcessor['Execute_POST.Arguments']):

        def getInitial(self,
                       args: PageArgs,
                       user: User
                       ) -> 'Execute_POST.Arguments':
            argsGET = cast(Execute_GET.Arguments, args)
            if argsGET.step is EntranceSteps.EDIT:
                return Execute_POST.Arguments.load(
                    self.configDB, self.taskDefDB, argsGET, user
                    )
            elif argsGET.config:
                path = ' '.join(step.name for step in self.page.steps[:2])
                return Execute_POST.Arguments.load(
                    self.configDB, self.taskDefDB, argsGET, user
                    ).override(path=path)
            else:
                return Execute_POST.Arguments()

class Execute_POST(ExecuteBase):

    class Arguments(DialogPage.Arguments):
        target = SetArg()
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

        @classmethod
        def load(cls,
                 configDB: ConfigDB,
                 taskDefDB: TaskDefDB,
                 args: Execute_GET.Arguments,
                 user: User
                 ) -> 'Execute_POST.Arguments':
            try:
                config = configDB[args.config]
            except KeyError:
                raise InvalidRequest(
                    f'Configuration "{args.config}" does not exist'
                    )

            checkPrivilege(user, 'c/a', 'access configurations')
            tasks = config.getTasks()

            values = {}
            poverride = {}
            runnerspt = {}
            for task in tasks:
                taskName = task.getName()
                taskDef = taskDefDB[taskName]
                for param in taskDef.getParameters().keys():
                    paramKey = taskName + '/' + param
                    value = task.getParameter(param)
                    values[paramKey] = value or ''
                    poverride[paramKey] = value is not None
                runners = task.getRunners()
                if runners:
                    runnerspt[taskName] = set(runners)

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

            return cls(
                config = config.getId(),
                target = config.targets,
                tasks = frozenset(
                    task['name']
                    for task in tasks
                    ),
                prio = {
                    task['name']: task['priority']
                    for task in tasks
                    },
                prod = {
                    prod['name']: prod.get('locator') or ''
                    for prod in config.getInputs()
                    },
                local = {
                    prod['name']: prod['localAt']
                    for prod in config.getInputs()
                    if prod.get('localAt') is not None
                    },
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

    class Processor(ExecuteProcessorMixin,
                    ContinuedDialogProcessor[Arguments]):

        jobDB: ClassVar[JobDB]

class TargetTable(CheckBoxesTable):
    name = 'target'
    columns = ('Target', )

    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[str, Sequence[XMLContent]]]:
        for target in sorted(project.getTargets()):
            yield target, ( target, )

class NotifyTable(RadioTable):
    name = 'onfail'
    columns = ('Notify by email when job has finished', )

    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[str, Sequence[XMLContent]]]:
        yield 'always', ( 'always', '\u00A0' )
        yield 'onfail', ( 'only if a task result is a warning or an error',
            '\u00A0' )
        yield 'onerror', ( 'only if a task result is an error', '\u00A0' )


class TaskTable(CheckBoxesTable):
    name = 'tasks'

    def iterColumns(self, **kwargs: object) -> Iterator[Column]:
        yield Column('Task ID')
        yield Column('Title')
        if project['taskprio']:
            yield Column('Priority')

    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[str, Sequence[XMLContent]]]:
        proc = cast(Execute_POST.Processor, kwargs['proc'])
        prio = cast(DictArgInstance[int], proc.args.prio)
        taskDefDB = proc.taskDefDB

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
                cells: List[XMLContent] = [ taskId, task.getTitle() ]
                if project['taskprio']:
                    cells.append(
                        textInput(
                            name = 'prio.' + taskId,
                            value = str(prio.get(taskId, 0)),
                            size = 5, maxlength = 6,
                            disabled = disabled,
                            ).present(**kwargs)
                        )
                yield taskId, cells

class ShowTaskRunnerSelectionTable(SingleCheckBoxTable):
    name = 'trselect'
    label = 'Show Task Runner selection page'

class TaskRunnerSelectionTable(CheckBoxesTable):
    name = 'runners'
    columns = 'Task Runner',

    def iterOptions(self, **kwargs: object
                    ) -> Iterator[Tuple[str, Sequence[XMLContent]]]:
        proc = cast(Execute_POST.Processor, kwargs['proc'])

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

        taskRunners = proc.iterTaskRunners()

        # Are there tasks with non-empty required capability set?
        if len(taskCapsList[0]) > 0:
            def capsMatch(runner: TaskRunner) -> bool:
                trCaps = runner.capabilities
                assert requiredCaps is not None
                if requiredCaps > trCaps:
                    return False
                trCapsLen = len(trCaps)
                for caps in taskCapsList:
                    if len(caps) > trCapsLen:
                        return False
                    elif caps <= trCaps:
                        return True
                return False
            taskRunners = (
                runner for runner in taskRunners if capsMatch(runner)
                )

        for runnerId in sorted(runner.getId() for runner in taskRunners):
            yield runnerId, ( runnerId, )

class TaskRunnersPerTaskTable(SingleCheckBoxTable):
    name = 'pertask'
    label = 'Specify Task Runners per task'

class ConfigInputTable(InputTable):

    def filterTaskRunner(self,
                         taskRunner: TaskRunner,
                         taskSet: TaskSetWithInputs,
                         group: Optional[LocalGroup],
                         inp: Input
                         ) -> bool:
        targets = cast(Config, taskSet).targets
        return (not targets or not targets.isdisjoint(taskRunner.targets)) and (
            group is None or group.canRunOn(taskRunner.getId())
            )

class ParamTable(ParamOverrideTable):

    def getParamCell(self,
                     taskId: str,
                     name: str,
                     curValue: str,
                     defValue: str,
                     **kwargs: object
                     ) -> ParamCell:
        return ParamCell(
            taskId + '/' + name, curValue or '', defValue
            )

class TaskRunnersTable(Table):
    columns = 'Task', 'Task Runners'

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        config = cast(Config, kwargs['config'])
        taskRunners = cast(Iterable[TaskRunner], kwargs['taskRunners'])
        runnersPerTask = cast(
            Mapping[str, AbstractSet[str]], kwargs['runnersPerTask']
            )
        for item in config.getTaskGroupSequence():
            caps = item.getNeededCaps()
            if isinstance(item, TaskGroup):
                tasks = item.getTaskSequence()
            else:
                tasks = (item,)
            runners = [
                runner.getId() for runner in taskRunners
                if caps <= runner.capabilities
                ]
            taskName = tasks[0].getName()
            listBox = selectionList(
                name='runnerspt.' + taskName,
                selected=runnersPerTask.get(taskName, frozenset()),
                size=max(min(len(runners), 4), len(tasks)),
                style='width:100%;'
                )[ runners ]
            yield taskName, cell(rowspan = len(tasks))[listBox]
            for task in tasks[1 : ]:
                yield task.getName(),

class ActionTable(RadioTable):
    name = 'action'
    columns = ('Execute now or Save', )

    def iterOptions(self, **kwargs: object) -> Iterator[Sequence[XMLContent]]:
        # The onchange event handlers are there to make sure the right
        # radio button is activated when text is pasted into an edit
        # box from the context menu (right mouse button).
        yield Actions.START, 'Execute now', (
            ', ',
            textInput(
                name = 'multi', size = 3,
                onchange = f"form['{self.name}'][0].checked=true"
                ).present(**kwargs),
            ' times (configuration will not be saved).'
            )
        yield Actions.TAGS, 'Save configuration', None

    def formatOption(self,
                     box: XML,
                     cells: Sequence[XMLContent]
                     ) -> XMLContent:
        label, rest = cells
        return cell[xhtml.label[box, ' ', label], rest]

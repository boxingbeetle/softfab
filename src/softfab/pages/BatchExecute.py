# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from enum import Enum
from typing import (
    AbstractSet, ClassVar, Collection, DefaultDict, Dict, Iterator, List,
    Mapping, Optional, Set, cast
)

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, Redirect
from softfab.configlib import Config, ConfigDB, Input, TaskSetWithInputs
from softfab.configview import (
    InputTable, SelectConfigsMixin, SimpleConfigTable, presentMissingConfigs
)
from softfab.datawidgets import DataTable
from softfab.formlib import actionButtons, hiddenInput, makeForm, textInput
from softfab.joblib import Job, JobDB
from softfab.pageargs import DictArg, EnumArg, RefererArg, StrArg
from softfab.pagelinks import createJobsURL
from softfab.paramview import ParamOverrideTable
from softfab.request import Request
from softfab.resourcelib import TaskRunner
from softfab.selectview import SelectArgs
from softfab.taskgroup import LocalGroup, ProductProto
from softfab.userlib import User, UserDB, checkPrivilege
from softfab.webgui import decoration
from softfab.xmlgen import XMLContent, xhtml

# TODO: The thing with FakeTask and FakeTaskSet is a quick trick to use
#       the existing code in joblib/configlib. A better solution is needed.

class InputConflict(Exception):
    pass

class FakeTask:

    def __init__(self, name: str, inputs: Mapping[str, Input]):
        super().__init__()
        self.__inputs = inputs
        self.__name = name

    def getName(self) -> str:
        return self.__name

    def getInputs(self) -> AbstractSet[str]:
        return set(self.__inputs.keys())

    def getOutputs(self) -> AbstractSet[str]:
        return set()

    def getPriority(self) -> int:
        return 0

    def getRunners(self) -> AbstractSet[str]:
        # This is only called from canRunOn(), which is not used by any code
        # in BatchExecute.
        # TODO: Find a type-safe way of handling this.
        assert False

class FakeTaskSet(TaskSetWithInputs[FakeTask]):

    def __init__(self) -> None:
        super().__init__()
        self.__targets: DefaultDict[str, Set[str]] = defaultdict(set)
        self.__index = 0

    def addConfig(self, config: Config) -> None:
        targets = config.targets
        for group_, inputList in config.getInputsGrouped():
            inputs = {}
            for cfgInput in inputList:
                inputName = cfgInput.getName()
                ownInput = self._inputs.get(inputName)
                if ownInput is not None:
                    locator = ownInput.getLocator()
                    if ownInput.isLocal():
                        self.__targets[inputName].update(targets)
                        localAt = ownInput.getLocalAt()
                        if localAt != cfgInput.getLocalAt():
                            localAt = None
                        if locator != cfgInput.getLocator() or locator is None:
                            locator = ''
                        ownInput.setLocator(locator, localAt)
                    elif locator != cfgInput.getLocator():
                        ownInput.setLocator('')
                else:
                    ownInput = cfgInput.clone()
                    self._inputs[inputName] = ownInput
                    self.__targets[inputName] = set(targets)
                inputs[inputName] = ownInput
            self.__index += 1
            fakeName = str(self.__index)
            self._tasks[fakeName] = FakeTask(fakeName, inputs)

    def getInputSet(self) -> AbstractSet[str]:
        return set(self._inputs)

    def getTargets(self, inp: Input) -> AbstractSet[str]:
        return self.__targets[inp.getName()]

    def getProduct(self, name: str) -> ProductProto:
        return self._inputs[name]

    def getRunners(self) -> AbstractSet[str]:
        return set()

class BatchConfigTable(SimpleConfigTable):
    # Disable tabs and sorting because it would clear the forms.
    tabOffsetField = None
    sortField = None
    showTargets = True
    showOwner = False

    def getRecordsToQuery(self, proc: PageProcessor) -> Collection[Config]:
        return cast(BatchExecute_GET.Processor, proc).configs

parentPage = 'LoadExecute'

class ParentArgs(SelectArgs):
    parentQuery = RefererArg(parentPage, shared=SelectArgs)

Actions = Enum('Actions', 'EXECUTE CANCEL')

submitButtons = xhtml.p[ actionButtons(Actions) ]

class BatchExecute_GET(FabPage['BatchExecute_GET.Processor',
                               'BatchExecute_GET.Arguments']):
    icon = 'IconExec'
    description = 'Execute Batch'
    linkDescription = False

    class Arguments(ParentArgs):
        pass

    class Processor(SelectConfigsMixin[ParentArgs], PageProcessor[ParentArgs]):

        configDB: ClassVar[ConfigDB]
        userDB: ClassVar[UserDB]

        notices: List[str]

        def initTaskSet(self) -> None:
            '''Initializes our `taskSet` attribute with a TaskSetWithInputs
            instance that contains all tasks from the given configurations.
            Problems should be appended to `notices`.
            If problems prevent the creation of `taskSet`, set it to None.
            '''
            # pylint: disable=attribute-defined-outside-init
            taskSet = FakeTaskSet()
            try:
                for config in self.configs:
                    taskSet.addConfig(config)
            except InputConflict as ex:
                self.notices.append(str(ex))
                self.taskSet = None
            else:
                self.taskSet = taskSet

        async def process(self, req: Request[ParentArgs], user: User) -> None:
            # pylint: disable=attribute-defined-outside-init
            self.notices = []
            self.params: Dict[str, Mapping[str, Mapping[str, str]]] = {}

            self.findConfigs(self.configDB)
            self.initTaskSet()

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/c')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield BatchConfigTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(BatchExecute_GET.Processor, kwargs['proc'])
        for notice in proc.notices:
            yield xhtml.p(class_ = 'notice')[ notice ]
        configs = proc.configs
        if configs:
            yield xhtml.h3[ 'Selected configurations:' ]
            yield BatchConfigTable.instance.present(**kwargs)

            taskSet = proc.taskSet
            if taskSet is None:
                yield xhtml.p[ 'Cannot execute because of conflict.' ]
            else:
                yield makeForm(args = ParentArgs.subset(proc.args))[
                    BatchInputTable.instance,
                    submitButtons,
                    decoration[
                        xhtml.hr,
                        ParamTable.instance,
                        # Second set of submit buttons after parameter tables.
                        submitButtons
                        ],
                    ( hiddenInput(name=f'config.{i:d}', value=cfg.getId())
                      for i, cfg in enumerate(configs) ),
                    ].present(taskSet=taskSet, **kwargs)
                return
        else:
            yield xhtml.h3[ 'No configurations selected' ]

        yield xhtml.p[
            xhtml.a(href=proc.args.refererURL or parentPage)[
                'Back to Configurations'
                ]
            ]

class BatchExecute_POST(BatchExecute_GET):

    class Arguments(ParentArgs):
        action = EnumArg(Actions)
        prod = DictArg(StrArg())
        local = DictArg(StrArg())
        lref = DictArg(StrArg())
        config = DictArg(StrArg())
        param = DictArg(StrArg(), separators = '///')

    class Processor(BatchExecute_GET.Processor):

        jobDB: ClassVar[JobDB]

        async def process(self, req: Request[ParentArgs], user: User) -> None:
            args = cast(BatchExecute_POST.Arguments, req.args)
            action = args.action

            if action is not Actions.EXECUTE:
                assert action is Actions.CANCEL, action
                raise Redirect(args.refererURL or parentPage)

            notices: List[str] = []
            # pylint: disable=attribute-defined-outside-init
            self.notices = notices

            # Parse inputs.
            local = cast(Mapping[str, str], args.local)
            locations = dict(local)
            for inpName, lref in cast(Mapping[str, str], args.lref).items():
                location = local.get(lref)
                if location is not None:
                    locations[inpName] = location
            missingIds = []
            params: Dict[str, Mapping[str, Mapping[str, str]]] = {}
            configs = []
            for index, configId in cast(Mapping[str, str], args.config).items():
                try:
                    config = self.configDB[configId]
                except KeyError:
                    missingIds.append(configId)
                else:
                    configs.append(config)
                    taskParameters = cast(
                        Mapping[str, Mapping[str, Mapping[str, str]]],
                        args.param
                        ).get(index)
                    if taskParameters is not None:
                        params[configId] = taskParameters
            self.params = params
            self.configs = configs
            if missingIds:
                notices.append(presentMissingConfigs(missingIds))

            self.initTaskSet()
            taskSet = self.taskSet
            if taskSet is not None:
                for inpName, locator in cast(Mapping[str, str],
                                             args.prod).items():
                    inp = taskSet.getInput(inpName)
                    assert inp is not None
                    inp.setLocator(locator)
                for inpName, location in locations.items():
                    inp = taskSet.getInput(inpName)
                    assert inp is not None
                    inp.setLocalAt(location)

            if not notices:
                # Create jobs.
                inputs = cast(Mapping[str, str], args.prod)
                userName = user.name
                jobs: List[Job] = []
                empty: Mapping[str, Mapping[str, str]] = {}
                for config in configs:
                    try:
                        jobs += config.createJobs(userName,
                            locators = inputs, localAt = locations,
                            taskParameters = params.get(config.getId(), empty)
                            )
                    except ValueError as ex:
                        notices.append(f'{config.getId()}: {ex}')

                if not notices:
                    # Commit created jobs to database and show them to user.
                    jobDB = self.jobDB
                    jobIds = []
                    for job in jobs:
                        jobDB.add(job)
                        jobIds.append(job.getId())
                    raise Redirect(createJobsURL(jobIds))

class BatchInputTable(InputTable):

    def filterTaskRunner(self,
                         taskRunner: TaskRunner,
                         taskSet: TaskSetWithInputs,
                         group: Optional[LocalGroup],
                         inp: Input
                         ) -> bool:
        targets = cast(FakeTaskSet, taskSet).getTargets(inp)
        return not targets or targets <= taskRunner.capabilities

    def present(self, **kwargs: object) -> XMLContent:
        tablePresentation = super().present(**kwargs)
        if tablePresentation:
            yield xhtml.h3[ 'Inputs for the jobs:' ]
            yield tablePresentation
            taskSet = cast(FakeTaskSet, kwargs['taskSet'])
            if taskSet.hasLocalInputs():
                yield xhtml.p[
                    'Please specify "Local at" for all local inputs.'
                    ]

class ParamTable(ParamOverrideTable):

    def getParamCell(self,
                     taskId: str,
                     name: str,
                     curValue: str,
                     defValue: str,
                     **kwargs: object
                     ) -> XMLContent:
        indexStr = cast(str, kwargs['indexStr'])
        return textInput(
            name='param/' + indexStr + '/' + taskId + '/' + name,
            value=defValue if curValue is None else curValue,
            size=72
            )

    def present(self, **kwargs: object) -> XMLContent:
        proc = cast(BatchExecute_GET.Processor, kwargs['proc'])

        # Because we're wrapped in a decoration, the presentation should
        # evaluate to False if there are only empty tables.
        presentation: List[XMLContent] = []
        for index, config in enumerate(proc.configs):
            configId = config.getId()
            taskParameters = proc.params.get(configId)
            tasks = []
            for task in config.getTasks():
                taskName = task.getName()
                taskParams: Optional[Mapping[str, str]] = None
                if taskParameters is not None:
                    taskParams = taskParameters.get(taskName)
                if taskParams is None:
                    taskParams = task.getVisibleParameters()
                tasks.append(( taskName, task.getDef(), taskParams ))
            table = super().present(
                indexStr=str(index), tasks=tasks, **kwargs
                )
            if table:
                presentation += (
                    xhtml.h3[ f'Parameters for "{configId}":' ],
                    table
                    )
        return presentation

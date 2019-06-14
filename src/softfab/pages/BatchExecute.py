# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from enum import Enum
from typing import (
    AbstractSet, DefaultDict, Iterator, Mapping, Optional, Set, cast
)

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, Redirect
from softfab.configlib import Config, Input, TaskSetWithInputs, configDB
from softfab.configview import (
    InputTable, SelectConfigsMixin, SimpleConfigTable, presentMissingConfigs
)
from softfab.datawidgets import DataTable
from softfab.formlib import actionButtons, hiddenInput, makeForm, textInput
from softfab.joblib import jobDB
from softfab.pageargs import DictArg, EnumArg, RefererArg, StrArg
from softfab.pagelinks import createJobsURL
from softfab.paramview import ParamOverrideTable
from softfab.resourcelib import TaskRunner
from softfab.selectview import SelectArgs
from softfab.taskgroup import LocalGroup
from softfab.userlib import User, checkPrivilege
from softfab.webgui import decoration
from softfab.xmlgen import XMLContent, xhtml

# TODO: The thing with FakeTask and FakeTaskSet is a quick trick to use
#       the existing code in joblib/configlib. A better solution is needed.

class InputConflict(Exception):
    pass

class FakeTask:

    def __init__(self, name: str, inputs: Mapping):
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
        TaskSetWithInputs.__init__(self)
        self.__targets = defaultdict(set) # type: DefaultDict[str, Set[str]]
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

class BatchConfigTable(SimpleConfigTable):
    # Disable tabs and sorting because it would clear the forms.
    tabOffsetField = None
    sortField = None
    showTargets = True
    showOwner = False

    def getRecordsToQuery(self, proc):
        return proc.configs

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

        def initTaskSet(self):
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

        def process(self, req, user):
            # pylint: disable=attribute-defined-outside-init
            self.notices = []
            self.params = {}

            self.findConfigs()
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
            yield xhtml.h2[ 'Selected configurations:' ]
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
                    ( hiddenInput(name='config.%d' % i, value=cfg.getId())
                      for i, cfg in enumerate(configs) ),
                    ].present(taskSet=taskSet, **kwargs)
                return
        else:
            yield xhtml.h2[ 'No configurations selected' ]

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

        def process(self, req, user):
            args = req.args
            action = args.action

            if action is not Actions.EXECUTE:
                assert action is Actions.CANCEL, action
                raise Redirect(args.refererURL or parentPage)

            # pylint: disable=attribute-defined-outside-init
            self.notices = notices = []

            # Parse inputs.
            inputs = args.prod
            locations = dict(args.local)
            for inp, lref in args.lref.items():
                location = args.local.get(lref)
                if location is not None:
                    locations[inp] = location
            missingIds = []
            self.params = params = {}
            self.configs = configs = []
            for index, configId in args.config.items():
                try:
                    config = configDB[configId]
                except KeyError:
                    missingIds.append(configId)
                else:
                    configs.append(config)
                    taskParameters = args.param.get(index)
                    if taskParameters is not None:
                        params[configId] = taskParameters
            if missingIds:
                notices.append(presentMissingConfigs(missingIds))

            self.initTaskSet()
            taskSet = self.taskSet
            if taskSet is not None:
                for inpName, locator in self.args.prod.items():
                    taskSet.getInput(inpName).setLocator(locator)
                for inpName, location in locations.items():
                    taskSet.getInput(inpName).setLocalAt(location)

            if not notices:
                # Create jobs.
                userName = user.name
                jobs = []
                for config in configs:
                    try:
                        jobs += config.createJobs(userName,
                            locators = inputs, localAt = locations,
                            taskParameters = params.get(config.getId(), {})
                            )
                    except ValueError as ex:
                        notices.append('%s: %s' % (config.getId(), ex))

                if not notices:
                    # Commit created jobs to database and show them to user.
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

    def present(self, *, taskSet, **kwargs):
        tablePresentation = super().present(taskSet=taskSet, **kwargs)
        if tablePresentation:
            yield xhtml.h2[ 'Inputs for the jobs:' ]
            yield tablePresentation
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

    def present(self, *, proc, **kwargs):
        # Because we're wrapped in a decoration, the presentation should
        # evaluate to False if there are only empty tables.
        presentation = []
        for index, config in enumerate(proc.configs):
            configId = config.getId()
            taskParameters = proc.params.get(configId)
            tasks = []
            for task in config.getTasks():
                taskName = task.getName()
                taskParams = None
                if taskParameters is not None:
                    taskParams = taskParameters.get(taskName)
                if taskParams is None:
                    taskParams = task.getParameters()
                tasks.append(( taskName, task.getDef(), taskParams ))
            table = super().present(
                proc=proc, indexStr=str(index), tasks=tasks, **kwargs
                )
            if table:
                presentation += (
                    xhtml.h2[ 'Parameters for "%s":' % configId ],
                    table
                    )
        return presentation

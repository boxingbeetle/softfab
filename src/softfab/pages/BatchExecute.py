# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, Redirect
from softfab.configlib import TaskSetWithInputs, configDB
from softfab.configview import (
    InputTable, SelectConfigsMixin, SimpleConfigTable, presentMissingConfigs
    )
from softfab.datawidgets import DataTable
from softfab.formlib import actionButtons, hiddenInput, makeForm, textInput
from softfab.joblib import jobDB
from softfab.paramview import ParamOverrideTable
from softfab.pageargs import DictArg, EnumArg, RefererArg, StrArg
from softfab.pagelinks import createJobsURL
from softfab.selectview import SelectArgs
from softfab.utils import encodeURL
from softfab.webgui import decoration
from softfab.xmlgen import xhtml

from enum import Enum

# TODO: The thing with FakeTask and FakeTaskSet is a quick trick to use
#       the existing code in joblib/configlib. A better solution is needed.

class InputConflict(Exception):
    pass

class FakeTask:

    def __init__(self, name, inputs):
        self.__inputs = inputs
        self.__name = name

    def isGroup(self):
        return False

    def getName(self):
        return self.__name

    def getInputs(self):
        return set(self.__inputs.keys())

    def getOutputs(self):
        return set()

    def getPriority(self):
        return 0

class FakeTaskSet(TaskSetWithInputs):

    def __init__(self):
        TaskSetWithInputs.__init__(self)
        self.__targets = {}
        self.__index = 0

    def addConfig(self, config):
        for group_, inputList in config.getInputsGrouped():
            inputs = {}
            for cfgInput in inputList:
                inputName = cfgInput['name']
                ownInput = self._inputs.get(inputName)
                if ownInput is not None:
                    locator = ownInput.get('locator')
                    if ownInput.isLocal():
                        # Assume: only one target per Task Runner is allowed.
                        if self.__targets[inputName] != config['target']:
                            raise InputConflict(
                                'The configurations can not be executed '
                                'because of conflicting local inputs'
                                )
                        localAt = ownInput.get('localAt')
                        if localAt != cfgInput.get('localAt'):
                            localAt = None
                        if locator != cfgInput.get('locator'):
                            locator = ''
                        ownInput.setLocator(locator, localAt)
                    elif locator != cfgInput.get('locator'):
                        ownInput.setLocator('')
                else:
                    ownInput = cfgInput.clone()
                    self._inputs[inputName] = ownInput
                    self.__targets[inputName] = config['target']
                inputs[inputName] = ownInput
            self.__index += 1
            fakeName = str(self.__index)
            self._tasks[fakeName] = FakeTask(fakeName, inputs)

    def getInputSet(self):
        return set(self._inputs)

    def getTarget(self, inp):
        return self.__targets.get(inp['name'])

class BatchConfigTable(SimpleConfigTable):
    # Disable tabs and sorting because it would clear the forms.
    tabOffsetField = None
    sortField = None

    def getRecordsToQuery(self, proc):
        return proc.configs

parentPage = 'LoadExecute'

class ParentArgs(SelectArgs):
    parentQuery = RefererArg(parentPage, excludes = SelectArgs)

Actions = Enum('Actions', 'EXECUTE CANCEL')

submitButtons = xhtml.p[ actionButtons(Actions) ]

class BatchExecute_GET(FabPage['BatchExecute_GET.Processor']):
    icon = 'IconExec'
    description = 'Execute Batch'
    linkDescription = False

    class Arguments(ParentArgs):
        pass

    class Processor(SelectConfigsMixin, PageProcessor):

        def getBackURL(self):
            parentQuery = self.args.parentQuery
            args = list(SelectArgs.subset(self.args).toQuery())
            if parentQuery is not None:
                args += parentQuery
            return '%s?%s' % ( parentPage, encodeURL(args) )

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

        def process(self, req):
            # pylint: disable=attribute-defined-outside-init
            self.notices = []
            self.params = {}

            self.findConfigs()
            self.initTaskSet()

    def checkAccess(self, req):
        req.checkPrivilege('j/c')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield BatchConfigTable.instance

    def presentContent(self, proc):
        for notice in proc.notices:
            yield xhtml.p(class_ = 'notice')[ notice ]
        configs = proc.configs
        if configs:
            yield xhtml.h2[ 'Selected configurations:' ]
            yield BatchConfigTable.instance.present(proc=proc)

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
                    ].present(proc=proc, taskSet=taskSet)
                return
        else:
            yield xhtml.h2[ 'No configurations selected' ]

        yield xhtml.p[
            xhtml.a(href = proc.getBackURL())[ 'Back to Configurations' ]
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

        def process(self, req):
            args = req.args
            action = args.action

            if action is not Actions.EXECUTE:
                assert action is Actions.CANCEL, action
                raise Redirect(self.getBackURL())

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
                userName = req.getUserName()
                jobs = []
                for config in configs:
                    try:
                        job = config.createJob(userName,
                            locators = inputs, localAt = locations,
                            taskParameters = params.get(config.getId())
                            )
                    except ValueError as ex:
                        notices.append('%s: %s' % (config.getId(), ex))
                    else:
                        jobs.append(job)

                if not notices:
                    # Commit created jobs to database and show them to user.
                    jobIds = []
                    for job in jobs:
                        jobDB.add(job)
                        jobIds.append(job.getId())
                    raise Redirect(createJobsURL(jobIds))

class BatchInputTable(InputTable):

    def filterTaskRunner(self, taskRunner, taskSet, group, inp):
        return taskRunner['target'] == taskSet.getTarget(inp)

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

    def getParamCell(self, proc, taskId, name, curValue, defValue):
        return textInput(
            name='param/' + proc.indexStr + '/' + taskId + '/' + name,
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
            assert not hasattr(proc, 'indexStr')
            proc.indexStr = str(index)
            assert not hasattr(proc, 'tasks')
            proc.tasks = tasks = []
            for task in config.getTasks():
                taskName = task.getName()
                taskParams = None
                if taskParameters is not None:
                    taskParams = taskParameters.get(taskName)
                if taskParams is None:
                    taskParams = task.getParameters()
                tasks.append(( taskName, task.getDef(), taskParams ))
            table = super().present(proc=proc, **kwargs)
            if table:
                presentation += (
                    xhtml.h2[ 'Parameters for "%s":' % configId ],
                    table
                    )
            del proc.indexStr
            del proc.tasks
        return presentation

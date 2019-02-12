# SPDX-License-Identifier: BSD-3-Clause

from softfab.config import enableSecurity, rootURL
from softfab.configlib import configDB
from softfab.databaselib import RecordObserver
from softfab.datawidgets import DataColumn, DataTable, LinkColumn
from softfab.formlib import dropDownList, emptyOption, hiddenInput, textInput
from softfab.joblib import jobDB
from softfab.jobview import unfinishedJobs
from softfab.pagelinks import createConfigDetailsLink, createJobURL
from softfab.productdeflib import ProductType
from softfab.projectlib import project
from softfab.schedulelib import scheduleDB
from softfab.sortedqueue import SortedQueue
from softfab.statuslib import StatusModel, StatusModelRegistry
from softfab.taskrunnerlib import taskRunnerDB
from softfab.userview import OwnerColumn
from softfab.webgui import Table, cell
from softfab.xmlgen import xml

class SelectConfigsMixin:
    '''Mixin for PageProcessors that want to use the `sel` argument to
    select configurations.
    '''

    def findConfigs(self):
        self.configs = configs = []
        missingIds = []
        for configId in sorted(self.args.sel):
            try:
                configs.append(configDB[configId])
            except KeyError:
                missingIds.append(configId)
        if missingIds:
            self.notices.append(presentMissingConfigs(missingIds))

def presentMissingConfigs(missingIds):
    return '%s not exist (anymore): %s' % (
        'Configuration does' if len(missingIds) == 1 else 'Configurations do',
        ', '.join(sorted(missingIds))
        )

class InputTable(Table):
    hideWhenEmpty = True

    def iterColumns(self, taskSet, **kwargs):
        yield 'Input'
        yield 'Locator'
        if taskSet.hasLocalInputs():
            yield 'Local at'

    def iterRows(self, taskSet, **kwargs):
        grouped = taskSet.getInputsGrouped()
        localInputs = taskSet.hasLocalInputs()
        taskRunners = None
        for group, groupInputs in grouped:
            first = None
            for inp in groupInputs:
                inputName = inp['name']
                cells = [ inputName ]
                prodType = inp.getType()
                local = inp.isLocal()
                locator = inp.get('locator') or ''
                if prodType is ProductType.TOKEN:
                    if local:
                        cells.append('token')
                    else:
                        # Global token: do not include this.
                        continue
                else:
                    # Note: This also acts as the fallback for file products
                    #       when the browser might not be able to handle a
                    #       more fancy presentation.
                    cells.append(textInput(
                        name='prod.' + inputName, value=locator, size=80
                        ))
                if localInputs and first is None:
                    if local:
                        if taskRunners is None:
                            taskRunners = sorted(
                                runnerId
                                for runnerId, runner in taskRunnerDB.items()
                                if self.filterTaskRunner(
                                    # TODO: Passing "inp" should not be needed,
                                    #       but this requires non-trivial
                                    #       changes in BatchExecute.
                                    runner, taskSet, group, inp
                                    )
                                )
                        cellData = dropDownList(
                            name='local.' + inputName,
                            selected=inp.get('localAt', ''),
                            required=True
                            )[
                            emptyOption(disabled=True)[
                                '(select Task Runner)'
                                ],
                            taskRunners
                            ]
                    else:
                        cellData = '-'
                    cells.append(cell(rowspan = len(groupInputs))[cellData])
                if first is None:
                    first = inputName
                elif local:
                    cells[0] = (
                        cells[0],
                        hiddenInput(name='lref.' + inputName, value=first)
                        )
                yield cells

    def filterTaskRunner(self, taskRunner, taskSet, group, inp):
        raise NotImplementedError

class _NameColumn(DataColumn):
    label = 'Configuration ID'
    keyName = 'name'
    def presentCell(self, record, **kwargs):
        return createConfigDetailsLink(record.getId())

class SimpleConfigTable(DataTable):
    db = configDB
    printRecordCount = False
    showConflictAsError = False
    '''If True, rows containing a configuration that is in conflict will be
    given the CSS class "error".'''

    fixedColumns = (
        _NameColumn(),
        DataColumn('#', 'nrtasks', cellStyle = 'rightalign'),
        DataColumn(keyName = 'description')
        )
    targetColumn = DataColumn(keyName = 'target')

    def iterColumns(self, **kwargs):
        yield from self.fixedColumns
        # TODO: Look at both project and config targets?
        if project.showTargets():
            yield self.targetColumn
        if enableSecurity:
            yield OwnerColumn.instance

    def iterRowStyles(self, rowNr, record, **kwargs):
        if self.showConflictAsError and not record.hasValidInputs():
            yield 'error'

class ConfigTable(SimpleConfigTable):

    def iterColumns(self, **kwargs):
        yield LinkColumn('Load', 'Execute', idArg = 'config')
        yield from super().iterColumns(**kwargs)
        yield LinkColumn(
            'Edit', 'Execute',
            idArg = 'config', extraArgs = ( ('step', 'edit'), )
            )
        yield LinkColumn('Delete', 'DelJobConfig')

def schedulesUsingConfig(configId):
    '''Iterates through the IDs of those schedules that explicitly refer to the
    configuration with the given ID. Tagged schedules are never included, no
    matter whether the configuration matches the tag or not.
    '''
    for scheduleId, schedule in scheduleDB.items():
        if schedule['configId'] == configId:
            yield scheduleId

class SortedJobsByConfig(SortedQueue):
    compareField = 'recent'

    def __init__(self, configId):
        self.__configId = configId
        SortedQueue.__init__(self, jobDB)

    def _filter(self, record):
        return record['configId'] == self.__configId

class ConfigJobModel(StatusModel):

    @classmethod
    def getChildClass(cls):
        return None

    def __recomputeJob(self, recentLimit):
        # Find the oldest non-final job.
        watched = None
        if recentLimit is None:
            configId = self.getId()
            retriever = jobDB.retrieverFor('configId')
            for job in unfinishedJobs:
                if retriever(job) == configId:
                    watched = job
                    break
        else:
            for job in self.__sortedJobsByConfig:
                if job['recent'] >= recentLimit:
                    break
                if not job.isExecutionFinished():
                    watched = job
        if watched is None:
            # All jobs have final result; watch the latest one.
            # Note: Because this class is instantiated only for those configIds
            #       in jobDB.uniqueValues('configId'), there is always at least
            #       one matching job.
            watched = self.__sortedJobsByConfig[0]
        return watched

    def _registerForUpdates(self):
        self.__sortedJobsByConfig = SortedJobsByConfig(self.getId())
        self.__job = self.__recomputeJob(None)

    def _unregisterForUpdates(self):
        self.__sortedJobsByConfig.retire()
        del self.__sortedJobsByConfig
        del self.__job

    def jobModified(self, job):
        # pylint: disable=attribute-defined-outside-init
        if job.getId() == self.__job.getId():
            if self.__job.isExecutionFinished():
                # Currently watched job has finished, get new one to watch.
                self.__job = self.__recomputeJob(self.__job['recent'])
            self._notify()
        else:
            if self.__job.isExecutionFinished():
                if job['recent'] < self.__job['recent']:
                    # A job was added, start watching the new job.
                    self.__job = job
                    self._notify()

    def formatStatus(self):
        job = self.__job
        return xml.status(
            health = job.getResult() or 'unknown',
            busy = 'true' if not job.isExecutionFinished() else 'false',
            url = rootURL + createJobURL(job.getId()),
            )

class ConfigJobModelGroup(StatusModel, RecordObserver):

    @classmethod
    def getChildClass(cls):
        return ConfigJobModel

    def __init__(self, modelId, parent):
        RecordObserver.__init__(self)
        StatusModel.__init__(self, modelId, parent)
        self.__keys = jobDB.uniqueValues('configId') - set([ None ])

    def _createModel(self, key):
        return ConfigJobModel(key, self)

    def _iterKeys(self):
        assert None not in self.__keys
        return iter(self.__keys)

    def _registerForUpdates(self):
        jobDB.addObserver(self)

    def _unregisterForUpdates(self):
        jobDB.removeObserver(self)

    def added(self, record):
        configId = record.getConfigId()
        if configId is not None:
            if configId not in self.__keys:
                self.__keys.add(configId)
                self._modelAdded(configId)
            child = self._children.get(configId)
            if child is not None:
                child.jobModified(record)

    def removed(self, record):
        assert False, 'job %s removed' % record.getId()

    def updated(self, record):
        configId = record.getConfigId()
        if configId is not None:
            child = self._children.get(configId)
            if child is not None:
                child.jobModified(record)

# This feature is experimental; it should only be enabled on hand-picked
# factories.
if False:
    StatusModelRegistry.instance.addModelGroup(
        ConfigJobModelGroup, 'job from configuration'
        )

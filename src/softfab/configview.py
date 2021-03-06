# SPDX-License-Identifier: BSD-3-Clause

from typing import Generic, Iterator, List, Optional, Sequence, TypeVar, cast

from softfab.configlib import Config, ConfigDB, Input, TaskSetWithInputs
from softfab.datawidgets import DataColumn, DataTable, LinkColumn
from softfab.formlib import dropDownList, emptyOption, hiddenInput, textInput
from softfab.pagelinks import createConfigDetailsLink
from softfab.productdeflib import ProductType
from softfab.projectlib import Project
from softfab.resourcelib import ResourceDB, TaskRunner
from softfab.restypeview import createTargetLink
from softfab.schedulelib import ScheduleDB
from softfab.selectview import SelectArgs
from softfab.taskgroup import LocalGroup
from softfab.userlib import UserDB
from softfab.userview import OwnerColumn
from softfab.webgui import Column, Table, cell
from softfab.xmlgen import XMLContent, xhtml

SelectArgsT = TypeVar('SelectArgsT', bound=SelectArgs)

class SelectConfigsMixin(Generic[SelectArgsT]):
    '''Mixin for PageProcessors that want to use the `sel` argument to
    select configurations.
    '''

    args: SelectArgsT
    notices: List[str]

    def findConfigs(self, configDB: ConfigDB) -> None:
        configs = []
        missingIds = []
        for configId in sorted(self.args.sel):
            try:
                configs.append(configDB[configId])
            except KeyError:
                missingIds.append(configId)
        self.configs = configs
        if missingIds:
            self.notices.append(presentMissingConfigs(missingIds))

def presentMissingConfigs(missingIds: Sequence[str]) -> str:
    return '%s not exist (anymore): %s' % (
        'Configuration does' if len(missingIds) == 1 else 'Configurations do',
        ', '.join(sorted(missingIds))
        )

class InputTable(Table):
    hideWhenEmpty = True

    def iterColumns(self, **kwargs: object) -> Iterator[Column]:
        taskSet = cast(TaskSetWithInputs, kwargs['taskSet'])
        yield Column('Input')
        yield Column('Locator')
        if taskSet.hasLocalInputs():
            yield Column('Local at')

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        taskSet = cast(TaskSetWithInputs, kwargs['taskSet'])
        grouped = taskSet.getInputsGrouped()
        localInputs = taskSet.hasLocalInputs()
        resourceDB: ResourceDB = getattr(kwargs['proc'], 'resourceDB')
        taskRunners = None
        for group, groupInputs in grouped:
            first: Optional[str] = None
            for inp in groupInputs:
                inputName = inp.getName()
                cells: List[XMLContent] = [ inputName ]
                prodType = inp.getType()
                local = inp.isLocal()
                locator = inp.getLocator() or ''
                if prodType is ProductType.TOKEN:
                    if local:
                        cells.append('token')
                    else:
                        # Global token: do not include this.
                        continue
                else:
                    cells.append(textInput(
                        name='prod.' + inputName, value=locator, size=80
                        ))
                if localInputs and first is None:
                    if local:
                        if taskRunners is None:
                            taskRunners = sorted(
                                runner.getId()
                                for runner in resourceDB.iterTaskRunners()
                                if self.filterTaskRunner(
                                    # TODO: Passing "inp" should not be needed,
                                    #       but this requires non-trivial
                                    #       changes in BatchExecute.
                                    runner, taskSet, group, inp
                                    )
                                )
                        cellData: XMLContent = dropDownList(
                            name='local.' + inputName,
                            selected=inp.getLocalAt() or '',
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

    def filterTaskRunner(self,
                         taskRunner: TaskRunner,
                         taskSet: TaskSetWithInputs,
                         group: Optional[LocalGroup],
                         inp: Input
                         ) -> bool:
        raise NotImplementedError

class _NameColumn(DataColumn[Config]):
    label = 'Configuration ID'
    keyName = 'name'
    def presentCell(self, record: Config, **kwargs: object) -> XMLContent:
        configDB: ConfigDB = getattr(kwargs['proc'], 'configDB')
        return createConfigDetailsLink(configDB, record.getId())

class TargetsColumn(DataColumn[Config]):
    keyName = 'targets'

    def presentCell(self, record: Config, **kwargs: object) -> XMLContent:
        targets = record.targets
        if targets:
            return xhtml[', '].join(
                createTargetLink(target)
                for target in sorted(targets)
                )
        else:
            return '-'

class SimpleConfigTable(DataTable[Config]):
    dbName = 'configDB'
    printRecordCount = False
    showConflictAsError = False
    '''If True, rows containing a configuration that is in conflict will be
    given the CSS class "error".'''
    showTargets = False
    """If False, the targets column will not be shown;
    if True, its visibility depends on project settings.
    """
    showOwner = True
    """If False, the owner column will not be shown;
    if True, its visibility depends on project settings.
    """

    fixedColumns = (
        _NameColumn(),
        DataColumn[Config]('#', 'nrtasks', cellStyle = 'rightalign'),
        DataColumn[Config](keyName = 'description')
        )

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn[Config]]:
        project: Project = getattr(kwargs['proc'], 'project')
        userDB: UserDB = getattr(kwargs['proc'], 'userDB')
        yield from self.fixedColumns
        if self.showTargets and project.showTargets:
            yield TargetsColumn.instance
        if self.showOwner and userDB.showOwners:
            yield OwnerColumn[Config].instance

    def iterRowStyles( # pylint: disable=unused-argument
                      self, rowNr: int, record: Config, **kwargs: object
                      ) -> Iterator[str]:
        if self.showConflictAsError and not record.hasValidInputs():
            yield 'error'

class ConfigTable(SimpleConfigTable):

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn[Config]]:
        yield LinkColumn('Load', 'Execute', idArg='config')
        yield from super().iterColumns(**kwargs)
        yield LinkColumn(
            'Edit', 'Execute', idArg='config', extraArgs=(('step', 'edit'),)
            )
        yield LinkColumn('Delete', 'DelJobConfig')

def schedulesUsingConfig(scheduleDB: ScheduleDB,
                         configId: str
                         ) -> Iterator[str]:
    '''Iterates through the IDs of those schedules that explicitly refer to the
    configuration with the given ID. Tagged schedules are never included, no
    matter whether the configuration matches the tag or not.
    '''
    for scheduleId, schedule in scheduleDB.items():
        if schedule.configId == configId:
            yield scheduleId

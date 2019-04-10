# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import DataColumn, DataTable
from softfab.pageargs import ArgsCorrected, IntArg
from softfab.pagelinks import (
    CapFilterArgs, createTaskDetailsLink, createTaskRunnerDetailsLink
)
from softfab.projectlib import project
from softfab.querylib import CustomFilter
from softfab.resourcelib import resourceDB
from softfab.resourceview import presentCapabilities
from softfab.restypelib import resTypeDB, taskRunnerResourceTypeName
from softfab.restypeview import ResTypeTableMixin
from softfab.taskdeflib import taskDefDB
from softfab.userlib import User, checkPrivilege
from softfab.utils import ResultKeeper
from softfab.webgui import Table, pageLink, row, vgroup
from softfab.xmlgen import XMLContent, txt, xhtml


class ResTypeTable(ResTypeTableMixin, Table):

    def iterRows(self, *, proc, **kwargs):
        args = proc.args
        active = proc.args.restype
        for value, name, desc in self.iterOptions(proc=proc, **kwargs):
            yield row(class_='match' if active == value else None)[
                pageLink('Capabilities', args.override(restype=value))[
                    name
                    ],
                desc
                ]

class NameColumn(DataColumn):
    cellStyle = 'nobreak'

    def presentCell(self, record, **kwargs):
        return createTaskRunnerDetailsLink(record.getId())

class CapabilitiesColumn(DataColumn):

    def presentHeader(self, **kwargs):
        return super().presentHeader(**kwargs)(style='width:62%')

    def presentCell(self, record, *, proc, **kwargs):
        args = proc.args
        return presentCapabilities(
            record[self.keyName],
            args.restype,
            lambda name, cap=args.cap: name == cap
            )

class ResourcesTable(DataTable):
    db = resourceDB
    columns = (
        NameColumn('Name', 'id'),
        CapabilitiesColumn('Capabilities', 'capabilities'),
        )
    tabOffsetField = 'first_tr'
    style = 'properties'

    def iterFilters(self, proc):
        yield CustomFilter(
            lambda res, typeName=proc.args.restype: res.typeName == typeName
            )

class CapabilityColumn(DataColumn):
    cellStyle = 'nobreak'

    def presentCell(self, record, *, proc, **kwargs):
        return presentCapabilities(
            [record[self.keyName]],
            proc.args.restype
            )

class ResourcesColumn(DataColumn):

    def presentCell(self, record, **kwargs):
        return txt(', ').join(
            createTaskRunnerDetailsLink(runnerId)
            for runnerId in sorted(record['resourceIds'])
            )

class TaskDefinitionsColumn(DataColumn):

    def presentCell(self, record, **kwargs):
        return txt(', ').join(
            createTaskDetailsLink(taskDefId)
            for taskDefId in sorted(record[self.keyName])
            )

class CapabilitiesTable(DataTable):
    db = None
    uniqueKeys = ('capability',)
    objectName = 'capabilities'
    tabOffsetField = 'first_cap'
    style = 'properties'

    columns = (
        CapabilityColumn('Capability', 'capability'),
        ResourcesColumn('Provided by Resources', 'taskDefIds'),
        TaskDefinitionsColumn('Required for Tasks', 'taskDefIds'),
        )

    def iterRowStyles(self, rowNr, record, *, proc, **kwargs):
        if record['capability'] == proc.args.cap:
            yield 'match'

    def getRecordsToQuery(self, proc):
        return proc.capMap

class Capabilities_GET(FabPage['Capabilities_GET.Processor',
                               'Capabilities_GET.Arguments']):
    # TODO: Think of a good icon.
    icon = 'TaskRunStat1'
    description = 'Capabilities'

    class Arguments(CapFilterArgs):
        first_tr = IntArg(0)
        first_cap = IntArg(0)
        sort = 'id',

    class Processor(PageProcessor['Capabilities_GET.Arguments']):

        def process(self, req, user):
            args = req.args

            typeName = args.restype

            capMap = ResultKeeper(
                lambda rcap: {
                    'capability': rcap,
                    'taskDefIds': set(),
                    'resourceIds': set(),
                    }
                )

            # Always include targets, even if there are no TRs for them.
            for target in project.getTargets():
                capMap[target]

            # Determine capabilities required for each task.
            for taskDefId, taskDef in taskDefDB.items():
                for record in (taskDef, taskDef.getFramework()):
                    for spec in record.resourceClaim.iterSpecsOfType(typeName):
                        for rcap in spec.capabilities:
                            capMap[rcap]['taskDefIds'].add(taskDefId)

            # Determine which resources are necessary for each task.
            for resource in (
                    resource for resource in resourceDB
                    if resource.typeName == typeName
                    ):
                resourceId = resource.getId()
                for cap in resource.capabilities:
                    capMap[cap]['resourceIds'].add(resourceId)

            cap = args.cap
            if cap and cap not in capMap:
                raise ArgsCorrected(args, cap='')

            # pylint: disable=attribute-defined-outside-init
            self.capMap = capMap.values()

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield ResourcesTable.instance
        yield CapabilitiesTable.instance

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'r/l')

    def presentContent(self, proc: Processor) -> XMLContent:
        resType = resTypeDB[proc.args.restype]
        yield vgroup[
            ResTypeTable.instance,
            xhtml.h2[
                'Resources of type ',
                xhtml.b[resType.presentationName], ':'
                ],
            ResourcesTable.instance,
            CapabilitiesTable.instance
            ].present(proc=proc)

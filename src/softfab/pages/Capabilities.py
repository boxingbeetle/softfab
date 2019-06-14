# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, MutableSet, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.datawidgets import DataColumn, DataTable
from softfab.pageargs import ArgsCorrected, IntArg
from softfab.pagelinks import (
    CapFilterArgs, createTaskDetailsLink, createTaskRunnerDetailsLink
)
from softfab.projectlib import project
from softfab.querylib import CustomFilter, RecordFilter
from softfab.request import Request
from softfab.resourcelib import ResourceBase, resourceDB
from softfab.resourceview import presentCapabilities
from softfab.restypelib import resTypeDB
from softfab.restypeview import ResTypeTableMixin
from softfab.taskdeflib import taskDefDB
from softfab.typing import Collection
from softfab.userlib import User, checkPrivilege
from softfab.utils import ResultKeeper
from softfab.webgui import Table, pageLink, row, vgroup
from softfab.xmlgen import XMLContent, XMLNode, txt, xhtml


class ResTypeTable(ResTypeTableMixin, Table):

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        args = cast(CapFilterArgs, getattr(kwargs['proc'], 'args'))
        active = args.restype
        for value, name, desc in self.iterOptions(**kwargs):
            yield row(class_='match' if active == value else None)[
                pageLink('Capabilities', args.override(restype=value))[
                    name
                    ],
                desc
                ]

class NameColumn(DataColumn[ResourceBase]):
    cellStyle = 'nobreak'

    def presentCell(self, record: ResourceBase, **kwargs: object) -> XMLContent:
        return createTaskRunnerDetailsLink(record.getId())

class CapabilitiesColumn(DataColumn[ResourceBase]):
    keyName = 'capabilities'

    def presentHeader(self, **kwargs: object) -> XMLNode:
        return super().presentHeader(**kwargs)(style='width:62%')

    def presentCell(self, record: ResourceBase, **kwargs: object) -> XMLContent:
        args = cast(CapFilterArgs, getattr(kwargs['proc'], 'args'))
        def highlight(name: str, cap: str = args.cap) -> bool:
            return name == cap
        return presentCapabilities(record.capabilities, args.restype, highlight)

class ResourcesTable(DataTable[ResourceBase]):
    db = resourceDB
    columns = (
        NameColumn('Name', 'id'),
        CapabilitiesColumn('Capabilities'),
        )
    tabOffsetField = 'first_tr'
    style = 'properties'

    def iterFilters(self, proc: PageProcessor) -> Iterator[RecordFilter]:
        def match(res: ResourceBase, typeName: str = proc.args.restype) -> bool:
            return res.typeName == typeName
        yield CustomFilter(match)

# TODO: NamedTuple would be a simpler solution here, but proper
#       type annotation support for that requires Python 3.6.
#       Also DataColumn currently doesn't support NamedTuple.
class CapInfo:
    """Information about a capability's use."""

    def __init__(self, capability: str):
        self.capability = capability
        self.taskDefIds = set() # type: MutableSet[str]
        self.resourceIds = set() # type: MutableSet[str]

    def __getitem__(self, key: str) -> object:
        return getattr(self, key)

class CapabilityColumn(DataColumn[CapInfo]):
    keyName = 'capability'
    cellStyle = 'nobreak'

    def presentCell(self, record: CapInfo, **kwargs: object) -> XMLContent:
        args = cast(CapFilterArgs, getattr(kwargs['proc'], 'args'))
        return presentCapabilities([record.capability], args.restype)

class ResourcesColumn(DataColumn[CapInfo]):
    keyName = 'resourceIds'

    def presentCell(self, record: CapInfo, **kwargs: object) -> XMLContent:
        return txt(', ').join(
            createTaskRunnerDetailsLink(runnerId)
            for runnerId in sorted(record.resourceIds)
            )

class TaskDefinitionsColumn(DataColumn[CapInfo]):
    keyName = 'taskDefIds'

    def presentCell(self, record: CapInfo, **kwargs: object) -> XMLContent:
        return txt(', ').join(
            createTaskDetailsLink(taskDefId)
            for taskDefId in sorted(record.taskDefIds)
            )

class CapabilitiesTable(DataTable[CapInfo]):
    db = None
    uniqueKeys = ('capability',)
    objectName = 'capabilities'
    tabOffsetField = 'first_cap'
    style = 'properties'

    columns = (
        CapabilityColumn('Capability'),
        ResourcesColumn('Provided by Resources'),
        TaskDefinitionsColumn('Required for Tasks'),
        )

    def iterRowStyles(self, rowNr: int, record: CapInfo, **kwargs: object
                      ) -> Iterator[str]:
        args = cast(CapFilterArgs, getattr(kwargs['proc'], 'args'))
        if record.capability == args.cap:
            yield 'match'

    def getRecordsToQuery(self, proc: PageProcessor) -> Collection[CapInfo]:
        return cast('Capabilities_GET.Processor', proc).capMap

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

        def process(self, req: Request[CapFilterArgs], user: User) -> None:
            args = req.args
            typeName = args.restype

            capMap = ResultKeeper(CapInfo) # type: ResultKeeper[str, CapInfo]

            # Always include targets, even if there are no TRs for them.
            for target in project.getTargets():
                capMap[target]

            # Determine capabilities required for each task.
            for taskDefId, taskDef in taskDefDB.items():
                for record in (taskDef, taskDef.getFramework()):
                    for spec in record.resourceClaim.iterSpecsOfType(typeName):
                        for rcap in spec.capabilities:
                            capMap[rcap].taskDefIds.add(taskDefId)

            # Determine which resources are necessary for each task.
            for resource in (
                    resource for resource in resourceDB
                    if resource.typeName == typeName
                    ):
                resourceId = resource.getId()
                for cap in resource.capabilities:
                    capMap[cap].resourceIds.add(resourceId)

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

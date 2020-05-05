# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from enum import Enum
from typing import DefaultDict, Iterator, List, Sequence, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.RecordDelete import DeleteArgs
from softfab.databaselib import Retriever
from softfab.datawidgets import (
    DataColumn, DataTable, LinkColumn, ListDataColumn, TableData
)
from softfab.formlib import makeForm, submitButton
from softfab.pageargs import EnumArg, IntArg, PageArgs, SortArg, StrArg
from softfab.pagelinks import createJobLink, createTaskInfoLink, createTaskLink
from softfab.request import Request
from softfab.resourcelib import ResourceBase, TaskRunner, resourceDB
from softfab.resourceview import (
    ResourceNameColumn, StatusColumn, getResourceStatus, presentCapabilities
)
from softfab.restypeview import iterResourceTypes, reservedTypes
from softfab.taskrunlib import taskRunDB
from softfab.userlib import User, checkPrivilege
from softfab.webgui import Widget, docLink, header, pageLink, pageURL, row
from softfab.xmlgen import XML, XMLContent, xhtml


class CapabilitiesColumn(ListDataColumn[ResourceBase]):
    def presentCell(self, record: ResourceBase, **kwargs: object) -> XMLContent:
        return presentCapabilities(record.capabilities, record.typeName)

def _getResourceReservedBy(resource: ResourceBase) -> str:
    if isinstance(resource, TaskRunner):
        taskRun = resource.getRun()
        if taskRun is not None:
            return 'T-' + taskRun.getId()
    else:
        if resource.isReserved():
            return cast(str, resource['reserved'])
    if resource.isSuspended():
        userName = resource.getChangedUser()
        assert userName is not None
        return 'Z-' + userName
    return ''

class ReservedByColumn(DataColumn[ResourceBase]):
    sortKey = cast(Retriever, staticmethod(_getResourceReservedBy))
    def presentCell(self, record: ResourceBase, **kwargs: object) -> XMLContent:
        if record.isReserved():
            # TODO: Create a generic reserved-by system that works for all
            #       resources types.
            if isinstance(record, TaskRunner):
                return createTaskLink(record)
            else:
                reservedBy = cast(str, record['reserved'])
                reservedType, reservedId = reservedBy.split('-', 1)
                if reservedType == 'J': # job
                    return createJobLink(reservedId)
                elif reservedType == 'T': # task
                    run = taskRunDB[reservedId]
                    return createTaskInfoLink(
                        run.getJob().getId(), run.getName()
                        )
                else:
                    assert False, reservedBy
                    return '?'
        elif record.isSuspended():
            return record.getChangedUser()
        else:
            return '-'

class ReserveColumn(DataColumn[ResourceBase]):
    def presentCell(self, record: ResourceBase, **kwargs: object) -> XMLContent:
        proc = cast(PageProcessor[PageArgs], kwargs['proc'])
        action = Actions.RESUME if record.isSuspended() else Actions.SUSPEND
        return makeForm(
            args=PostArgs(proc.args, resource=record.getId()),
            setFocus=False
            )[ submitButton(name='action', value=action) ]

class EditColumn(DataColumn[ResourceBase]):
    def presentCell(self, record: ResourceBase, **kwargs: object) -> XMLContent:
        typeName = record.typeName
        if typeName.startswith('sf.'):
            for resType in reservedTypes:
                if resType.name == typeName:
                    pageName = resType.editPage
                    break
            else:
                return '-'
        else:
            pageName = 'ResourceEdit'
        return pageLink(pageName, DeleteArgs(id=record.getId()))[ 'Edit' ]

class ResourcesTable(DataTable[ResourceBase]):
    widgetId = 'resourcesTable'
    autoUpdate = True
    db = resourceDB
    fixedColumns: Sequence[DataColumn[ResourceBase]] = (
        ResourceNameColumn.instance,
        CapabilitiesColumn(keyName = 'capabilities'),
        StatusColumn(keyName = 'state', cellStyle = 'strong'),
        ReservedByColumn('Reserved By', 'reserved'),
        )
    reserveColumn = ReserveColumn('Action')
    # TODO: These can be used again when the TR-specific pages have been
    #       replaced.
    #editColumn = LinkColumn('Edit', 'ResourceEdit')
    editColumn = EditColumn('Edit')
    deleteColumn = LinkColumn[ResourceBase]('Delete', 'ResourceDelete')

    def iterColumns(self,
                    **kwargs: object
                    ) -> Iterator[DataColumn[ResourceBase]]:
        proc = cast(PageProcessor, kwargs['proc'])
        yield from self.fixedColumns
        user = proc.user
        if user.hasPrivilege('r/a'):
            yield self.reserveColumn
        if user.hasPrivilege('r/m'):
            yield self.editColumn
        if user.hasPrivilege('r/d'):
            yield self.deleteColumn

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        data = cast(TableData[ResourceBase], kwargs['data'])
        recordsByType: DefaultDict[str, List[ResourceBase]] = \
                defaultdict(list)
        for record in data.records:
            recordsByType[record.typeName].append(record)

        columns = data.columns
        numColumns = sum(column.colSpan for column in columns)
        for resType in iterResourceTypes():
            resTypeName = resType.getId()
            if resTypeName in recordsByType:
                yield row[header(colspan=numColumns, class_='section')[
                    resType.presentationName
                    ]]
                for record in recordsByType[resTypeName]:
                    yield row(class_=getResourceStatus(record))[(
                        column.presentCell(record, **kwargs)
                        for column in columns
                        )]

class ResourceIndex_GET(FabPage['ResourceIndex_GET.Processor',
                                'ResourceIndex_GET.Arguments']):
    icon = 'IconResources'
    description = 'Resources'
    children = [
        'ResourceNew', 'ResourceEdit', 'TaskRunnerEdit', 'RepoEdit',
        'ResourceDelete', 'Capabilities',
        'TaskRunnerDetails', 'TaskRunnerHistory'
        ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor['ResourceIndex_GET.Arguments']):
        pass

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'r/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield ResourcesTable.instance

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        yield ResourcesTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield ResourcesTable.instance.present(**kwargs)
        yield xhtml.p[
            'For help about resources read this section of the ',
            docLink('/start/user_manual/#resources')[ 'User Manual' ],
            '.'
            ]
        yield xhtml.p[
            'Download the ',
            xhtml.a(href='taskrunner.jar')['Task Runner JAR'],
            '.'
            ]

class PostArgs(ResourceIndex_GET.Arguments):
    resource = StrArg()

Actions = Enum('Actions', 'SUSPEND RESUME')

class ResourceIndex_POST(FabPage['ResourceIndex_POST.Processor',
                                 'ResourceIndex_POST.Arguments']):
    icon = 'IconResources'
    description = 'Resources'

    class Arguments(PostArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor['ResourceIndex_POST.Arguments']):

        async def process(self,
                          req: Request['ResourceIndex_POST.Arguments'],
                          user: User
                          ) -> None:
            args = req.args

            # Get resource record.
            resource = self.getResource(args.resource)

            # Update suspend state.
            resource.setSuspend(
                args.action is Actions.SUSPEND,
                user.name or 'anonymous'
                )

            # Show new status, forget commands.
            raise Redirect(pageURL(
                'ResourceIndex',
                ResourceIndex_GET.Arguments.subset(args)
                ))

        def getResource(self, resourceId: str) -> ResourceBase:
            try:
                return resourceDB[resourceId]
            except KeyError:
                raise PresentableError(xhtml.p[
                    'Resource ', xhtml.b[ resourceId ],
                    ' does not exist (anymore).'
                    ])

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'r/a', 'reserve resources')

    def presentContent(self, **kwargs: object) -> XMLContent:
        assert False

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield message
        yield self.backToSelf()

# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from enum import Enum
from typing import Iterator, Sequence, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.RecordDelete import DeleteArgs
from softfab.datawidgets import (
    DataColumn, DataTable, LinkColumn, ListDataColumn
)
from softfab.formlib import makeForm, submitButton
from softfab.pageargs import EnumArg, IntArg, PageArgs, SortArg, StrArg
from softfab.pagelinks import createTaskLink, createTaskRunnerDetailsLink
from softfab.resourcelib import ResourceBase, resourceDB
from softfab.resourceview import getResourceStatus, presentCapabilities
from softfab.restypelib import resTypeDB, taskRunnerResourceTypeName
from softfab.userlib import User, checkPrivilege
from softfab.webgui import Widget, docLink, header, pageLink, pageURL, row
from softfab.xmlgen import XML, XMLContent, xhtml


class NameColumn(DataColumn[ResourceBase]):
    def presentCell(self, record, **kwargs):
        if record.typeName == taskRunnerResourceTypeName:
            return createTaskRunnerDetailsLink(record.getId())
        else:
            return record.getId()

class CapabilitiesColumn(ListDataColumn[ResourceBase]):
    def presentCell(self, record, **kwargs):
        return presentCapabilities(record.capabilities, record.typeName)

class StateColumn(DataColumn[ResourceBase]):
    @staticmethod
    def sortKey(record):
        return getResourceStatus(record)
    def presentCell(self, record, **kwargs):
        return getResourceStatus(record)

class ReservedByColumn(DataColumn[ResourceBase]):
    def presentCell(self, record, **kwargs):
        if record.isReserved():
            if record.typeName == taskRunnerResourceTypeName:
                return createTaskLink(record)
            else:
                return record['user']
        elif record.isSuspended():
            return record['changeduser']
        else:
            return '-'

class ReserveColumn(DataColumn[ResourceBase]):
    def presentCell(self, record, *, proc, **kwargs):
        action = Actions.RESUME if record.isSuspended() else Actions.SUSPEND
        return makeForm(
            args=PostArgs(proc.args, resource=record.getId()),
            setFocus=False
            )[ submitButton(name='action', value=action) ]

class EditColumn(DataColumn[ResourceBase]):
    def presentCell(self, record, **kwargs):
        pageName = (
            'TaskRunnerEdit'
            if record.typeName == taskRunnerResourceTypeName
            else 'ResourceEdit'
            )
        return pageLink(pageName, DeleteArgs(id=record.getId()))[ 'Edit' ]

class ResourcesTable(DataTable[ResourceBase]):
    widgetId = 'resourcesTable'
    autoUpdate = True
    db = resourceDB
    fixedColumns = (
        NameColumn('Name', 'id'),
        DataColumn[ResourceBase](keyName = 'locator'),
        CapabilitiesColumn(keyName = 'capabilities'),
        StateColumn(keyName = 'state', cellStyle = 'strong'),
        ReservedByColumn('Reserved By', 'user'),
        ) # type: Sequence[DataColumn[ResourceBase]]
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

    def iterRows(self, *, data, **kwargs):
        recordsByType = defaultdict(list)
        for record in data.records:
            recordsByType[record.typeName].append(record)

        columns = data.columns
        numColumns = sum(column.colSpan for column in columns)
        resTypeNames = sorted(resTypeDB.keys())
        resTypeNames.remove(taskRunnerResourceTypeName)
        resTypeNames.insert(0, taskRunnerResourceTypeName)
        for resTypeName in resTypeNames:
            if resTypeName in recordsByType:
                resType = resTypeDB[resTypeName]
                yield row[header(colspan=numColumns, class_='section')[
                    resType.presentationName
                    ]]
                for record in recordsByType[resTypeName]:
                    yield row(class_=getResourceStatus(record))[(
                        column.presentCell(record, data=data, **kwargs)
                        for column in columns
                        )]

class ResourceIndex_GET(FabPage['ResourceIndex_GET.Processor',
                                'ResourceIndex_GET.Arguments']):
    icon = 'IconResources'
    description = 'Resources'
    children = [
        'ResourceNew', 'ResourceEdit', 'TaskRunnerEdit', 'ResourceDelete',
        'StorageIndex', 'Capabilities', 'TaskRunnerDetails', 'TaskRunnerHistory'
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

    def presentContent(self, proc: Processor) -> XMLContent:
        yield ResourcesTable.instance.present(proc=proc)
        yield xhtml.p[
            'The Task Runner installation package can be found on the ',
            docLink('/installation/downloads/#taskrunner_downloads')[
                'downloads page'
                ],
            '.'
            ]
        yield xhtml.p[
            'For help about "Resources" or "Resource Types" read the '
            'document: ',
            docLink('/reference/user_manual/#resources')[ 'Resources' ],
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

        def process(self, req, user):
            args = req.args

            # Get resource record.
            resource = self.getResource(args.resource)

            # Update suspend state.
            resource.setSuspend(args.action is Actions.SUSPEND, user.name)

            # Show new status, forget commands.
            raise Redirect(pageURL(
                'ResourceIndex',
                ResourceIndex_GET.Arguments.subset(args)
                ))

        def getResource(self, resourceId):
            try:
                return resourceDB[resourceId]
            except KeyError:
                raise PresentableError(xhtml.p[
                    'Resource ', xhtml.b[ resourceId ],
                    ' does not exist (anymore).'
                    ])

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'r/a', 'reserve resources')

    def presentContent(self, proc: Processor) -> XMLContent:
        assert False

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield message
        yield self.backToSelf()

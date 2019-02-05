# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from Page import PageProcessor, PresentableError, Redirect
from RecordDelete import DeleteArgs
from datawidgets import DataColumn, DataTable, LinkColumn, ListDataColumn
from formlib import makeForm, submitButton
from pageargs import EnumArg, IntArg, PageArgs, SortArg, StrArg
from pagelinks import createTaskLink, createTaskRunnerDetailsLink
from resourcelib import resourceDB
from resourceview import getResourceStatus, presentCapabilities
from restypelib import resTypeDB, taskRunnerResourceTypeName
from taskrunnerlib import taskRunnerDB
from webgui import docLink, header, pageLink, pageURL, row
from xmlgen import xhtml

from collections import defaultdict
from enum import Enum

class NameColumn(DataColumn):
    def presentCell(self, record, **kwargs):
        if record.typeName == taskRunnerResourceTypeName:
            return createTaskRunnerDetailsLink(record.getId())
        else:
            return record.getId()

class CapabilitiesColumn(ListDataColumn):
    def presentCell(self, record, **kwargs):
        return presentCapabilities(record.capabilities, record.typeName)

class StateColumn(DataColumn):
    sortKey = staticmethod(getResourceStatus)
    def presentCell(self, record, **kwargs):
        return getResourceStatus(record)

class ReservedByColumn(DataColumn):
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

class ReserveColumn(DataColumn):
    def presentCell(self, record, proc, **kwargs):
        action = Actions.RESUME if record.isSuspended() else Actions.SUSPEND
        return makeForm(
            args=PostArgs(proc.args, resource=record.getId()),
            setFocus=False
            )[ submitButton(name='action', value=action) ]

class EditColumn(DataColumn):
    def presentCell(self, record, **kwargs):
        pageName = (
            'TaskRunnerEdit'
            if record.typeName == taskRunnerResourceTypeName
            else 'ResourceEdit'
            )
        return pageLink(pageName, DeleteArgs(id=record.getId()))[ 'Edit' ]

class DeleteColumn(DataColumn):
    def presentCell(self, record, **kwargs):
        pageName = (
            'DelTaskRunnerRecord'
            if record.typeName == taskRunnerResourceTypeName
            else 'ResourceDelete'
            )
        return pageLink(pageName, DeleteArgs(id=record.getId()))[ 'Delete' ]

class ResourcesTable(DataTable):
    widgetId = 'resourcesTable'
    autoUpdate = True
    db = None
    uniqueKeys = ('id',)
    objectName = 'resources'
    fixedColumns = (
        NameColumn('Name', 'id'),
        DataColumn(keyName = 'locator'),
        CapabilitiesColumn(keyName = 'capabilities'),
        StateColumn(keyName = 'state', cellStyle = 'strong'),
        ReservedByColumn('Reserved By', 'user'),
        )
    reserveColumn = ReserveColumn('Action')
    # TODO: These can be used again when the TR-specific pages have been
    #       replaced.
    #editColumn = LinkColumn('Edit', 'ResourceEdit')
    editColumn = EditColumn('Edit')
    #deleteColumn = LinkColumn('Delete', 'ResourceDelete')
    deleteColumn = DeleteColumn('Delete')

    def getRecordsToQuery(self, proc):
        yield from resourceDB
        yield from taskRunnerDB

    def iterColumns(self, proc, **kwargs):
        yield from self.fixedColumns
        user = proc.req.getUser()
        if user.hasPrivilege('r/a'):
            yield self.reserveColumn
        if user.hasPrivilege('r/m'):
            yield self.editColumn
        if user.hasPrivilege('r/d'):
            yield self.deleteColumn

    def iterRows(self, data, **kwargs):
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
                    resType['presentation']
                    ]]
                for record in recordsByType[resTypeName]:
                    yield row(class_=getResourceStatus(record))[(
                        column.presentCell(record, data=data, **kwargs)
                        for column in columns
                        )]

class ResourceIndex_GET(FabPage):
    icon = 'IconResources'
    description = 'Resources'
    children = [
        'ResourceEdit', 'ResourceDelete', 'Capabilities', 'TaskRunnerDetails',
        'TaskRunnerEdit', 'TaskRunnerHistory', 'DelTaskRunnerRecord'
        ]

    class Arguments(PageArgs):
        first = IntArg(0)
        sort = SortArg()

    class Processor(PageProcessor):
        pass

    def checkAccess(self, req):
        req.checkPrivilege('r/l')

    def iterDataTables(self, proc):
        yield ResourcesTable.instance

    def iterWidgets(self, proc):
        yield ResourcesTable

    def presentContent(self, proc):
        yield ResourcesTable.instance.present(proc=proc)
        yield xhtml.p[
            'The Task Runner installation package can be found on the ',
            docLink('/downloads/#taskrunner_downloads')[ 'downloads page' ], '.'
            ]
        yield xhtml.p[
            'For help about "Resources" or "Resource Types" read the '
            'document: ',
            docLink('/reference/user_manual/#resources')[ 'Resources' ], '.'
            ]

class PostArgs(ResourceIndex_GET.Arguments):
    resource = StrArg()

Actions = Enum('Actions', 'SUSPEND RESUME')

class ResourceIndex_POST(FabPage):
    icon = 'IconResources'
    description = 'Resources'

    class Arguments(PostArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor):

        def process(self, req):
            args = req.args

            # Get resource record.
            resource = self.getResource(args.resource)

            # Update suspend state.
            userName = req.getUserName()
            resource.setSuspend(args.action is Actions.SUSPEND, userName)

            # Show new status, forget commands.
            raise Redirect(pageURL(
                'ResourceIndex',
                ResourceIndex_GET.Arguments.subset(args)
                ))

        def getResource(self, resourceId):
            try:
                return resourceDB[resourceId]
            except KeyError:
                try:
                    return taskRunnerDB[resourceId]
                except KeyError:
                    raise PresentableError(xhtml.p[
                        'Resource ', xhtml.b[ resourceId ],
                        ' does not exist (anymore).'
                        ])

    def checkAccess(self, req):
        req.checkPrivilege('r/a', 'reserve resources')

    def presentContent(self, proc):
        assert False

    def presentError(self, proc, message):
        yield message
        yield self.backToSelf()

# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.configlib import Config, configDB
from softfab.configview import ConfigTable, SimpleConfigTable
from softfab.datawidgets import DataColumn, DataTable
from softfab.formlib import checkBox
from softfab.pageargs import IntArg, SortArg
from softfab.projectlib import project
from softfab.selectview import (
    BasketArgs, SelectProcMixin, TagArgs, selectDialog
    )
from softfab.webgui import docLink
from softfab.xmlgen import xhtml

class SelectColumn(DataColumn):
    keyName = None
    label = None

    def presentCell(self, record, *, selectName, selectFunc, **kwargs):
        recordId = record.getId()
        checked, enabled = selectFunc(recordId)
        return checkBox(
            name=selectName, value=recordId, checked=checked,
            disabled=not enabled
            )

class BaseTagConfigTable(ConfigTable):
    showConflictAsError = True

    def _simpleMode(self, proc):
        raise NotImplementedError

    def iterRowStyles(self, rowNr, record, *, getRowStyle, **kwargs):
        yield from super().iterRowStyles(rowNr, record, **kwargs)
        style = getRowStyle(record)
        if style is not None:
            yield style

    def iterColumns(self, proc, **kwargs):
        tableClass = (
            SimpleConfigTable if self._simpleMode(proc) else ConfigTable
            )
        yield SelectColumn.instance
        yield from tableClass.iterColumns(self, proc=proc, **kwargs)

class TagConfigTable(BaseTagConfigTable):

    def _simpleMode(self, proc):
        # If there is a basket, use simple mode, otherwise full mode.
        return len(Config.cache.getKeys()) != 0 and len(proc.selected) > 0

    def getRecordsToQuery(self, proc):
        return proc.filteredRecords

class BasketConfigTable(BaseTagConfigTable):
    sortField = 'sort_basket'
    tabOffsetField = None

    def _simpleMode(self, proc):
        return True

    def getRecordsToQuery(self, proc):
        return proc.selectedRecords

class LoadExecute_GET(FabPage['LoadExecute_GET.Processor']):
    icon = 'IconExec'
    description = 'Execute'
    children = [
        'Execute', 'DelJobConfig', 'FastExecute', 'BatchExecute', 'ConfigTags',
        'ConfigDetails'
        ]

    class Arguments(TagArgs, BasketArgs):
        first = IntArg(0)
        sort = SortArg()
        sort_basket = SortArg()

    class Processor(PageProcessor, SelectProcMixin):
        tagCache = Config.cache
        db = configDB

        def iterActions(self):
            if project.getTagKeys():
                yield 'tags', 'Edit Tags...', 'ConfigTags'
            yield 'execute', 'Execute...', 'BatchExecute'

        def process(self, req):
            self.processSelection()

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield TagConfigTable.instance
        yield BasketConfigTable.instance

    def checkAccess(self, req):
        req.checkPrivilege('c/l')

    def presentContent(self, proc):
        yield xhtml.h2[ 'Execute from Configuration' ],
        yield selectDialog(
            proc, self.name, Config.cache,
            TagConfigTable.instance, BasketConfigTable.instance,
            'Configurations to Tag or Execute'
            )
        yield xhtml.p[
            'Read here more about: ',
            docLink('/reference/user-manual/#execute')[
                'Execute from Configuration'
                ]
            ]

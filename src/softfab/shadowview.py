# SPDX-License-Identifier: BSD-3-Clause

from softfab.datawidgets import (
    DataColumn, DataTable, DurationColumn, TimeColumn
)
from softfab.pagelinks import createTaskRunnerDetailsLink
from softfab.shadowlib import maxDoneRecords, maxOKRecords, shadowDB
from softfab.webgui import maybeLink
from softfab.xmlgen import xhtml


def getShadowRunStatus(run):
    state = run['state']
    if state == 'done':
        return run['result'].name.lower()
    else:
        return state

class _DescriptionColumn(DataColumn):
    keyName = 'description'

    def presentCell(self, record, **kwargs):
        return maybeLink(record.getURL())[ record['description'] ]

class _LocationColumn(DataColumn):
    keyName = 'location'

    def presentCell(self, record, **kwargs):
        return createTaskRunnerDetailsLink(record['location'])

class ShadowTable(DataTable):
    widgetId = 'shadowTable'
    autoUpdate = True
    db = shadowDB
    columns = (
        TimeColumn(
            keyName = '-createtime', keyDisplay = 'createtime',
            label = 'Create Time'
            ),
        DurationColumn(keyName = 'duration'),
        _DescriptionColumn.instance,
        _LocationColumn.instance,
        )

    def iterRowStyles(self, rowNr, record, **kwargs):
        yield getShadowRunStatus(record)

trimPolicy = xhtml.p[
    xhtml.br.join((
        'Automatic cleanup policy:',
        'Finished shadow runs exceeding the number of %d are removed;'
        % maxDoneRecords,
        'Successful (green) shadow runs exceeding the number of %d are removed.'
        % maxOKRecords
        ))
    ]

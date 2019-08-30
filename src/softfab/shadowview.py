# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, cast

from softfab.datawidgets import (
    DataColumn, DataTable, DurationColumn, TimeColumn
)
from softfab.pagelinks import createTaskRunnerDetailsLink
from softfab.shadowlib import ShadowRun, maxDoneRecords, maxOKRecords, shadowDB
from softfab.webgui import maybeLink
from softfab.xmlgen import XMLContent, xhtml


def getShadowRunStatus(run: ShadowRun) -> str:
    if run.isDone():
        result = run.getResult()
        assert result is not None
        return result.name.lower()
    else:
        return cast(str, run['state'])

class _DescriptionColumn(DataColumn[ShadowRun]):
    keyName = 'description'

    def presentCell(self, record: ShadowRun, **kwargs: object) -> XMLContent:
        return maybeLink(record.getURL())[ record.getDescription() ]

class _LocationColumn(DataColumn[ShadowRun]):
    keyName = 'location'

    def presentCell(self, record: ShadowRun, **kwargs: object) -> XMLContent:
        return createTaskRunnerDetailsLink(record.getLocation())

class ShadowTable(DataTable[ShadowRun]):
    widgetId = 'shadowTable'
    autoUpdate = True
    db = shadowDB
    columns = (
        TimeColumn[ShadowRun](
            keyName = '-createtime', keyDisplay = 'createtime',
            label = 'Create Time'
            ),
        DurationColumn[ShadowRun](keyName = 'duration'),
        _DescriptionColumn.instance,
        _LocationColumn.instance,
        )

    def iterRowStyles(self,
                      rowNr: int,
                      record: ShadowRun,
                      **kwargs: object
                      ) -> Iterator[str]:
        yield getShadowRunStatus(record)

trimPolicy = xhtml.p[
    xhtml.br.join((
        'Automatic cleanup policy:',
        'Finished shadow runs exceeding '
            f'the number of {maxDoneRecords:d} are removed;',
        'Successful (green) shadow runs exceeding '
            f'the number of {maxOKRecords:d} are removed.'
        ))
    ]

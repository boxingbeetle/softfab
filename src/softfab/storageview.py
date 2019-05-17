# SPDX-License-Identifier: BSD-3-Clause

from softfab.datawidgets import DataColumn, DataTable, LinkColumn
from softfab.storagelib import Storage, storageDB
from softfab.xmlgen import XMLContent, xhtml


class _URLColumn(DataColumn[Storage]):
    keyName = 'url'
    label = 'URL'

    def presentCell(self, record: Storage, **kwargs: object) -> XMLContent:
        url = record.getURL()
        return xhtml.a(href=url)[ url ]

class StorageTable(DataTable[Storage]):
    db = storageDB
    columns = (
        DataColumn[Storage](keyName = 'name'),
        _URLColumn.instance,
        LinkColumn[Storage]('Edit', 'StorageEdit'),
        )

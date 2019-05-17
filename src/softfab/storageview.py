# SPDX-License-Identifier: BSD-3-Clause

from softfab.datawidgets import DataColumn, DataTable, LinkColumn
from softfab.storagelib import Storage, storageDB
from softfab.xmlgen import xhtml


class _URLColumn(DataColumn[Storage]):
    keyName = 'url'
    label = 'URL'

    def presentCell(self, record, **kwargs):
        url = record['url']
        return xhtml.a(href = url)[ url ]

class StorageTable(DataTable):
    db = storageDB
    columns = (
        DataColumn[Storage](keyName = 'name'),
        _URLColumn.instance,
        LinkColumn[Storage]('Edit', 'StorageEdit'),
        )

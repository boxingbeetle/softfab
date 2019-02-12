# SPDX-License-Identifier: BSD-3-Clause

from softfab.datawidgets import DataColumn, DataTable, LinkColumn
from softfab.storagelib import storageDB
from softfab.xmlgen import xhtml

class _URLColumn(DataColumn):
    keyName = 'url'
    label = 'URL'

    def presentCell(self, record, **kwargs):
        url = record['url']
        return xhtml.a(href = url)[ url ]

class StorageTable(DataTable):
    db = storageDB
    columns = (
        DataColumn(keyName = 'name'),
        _URLColumn.instance,
        LinkColumn(label = 'Edit', page = 'StorageEdit'),
        )

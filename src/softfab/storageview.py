# SPDX-License-Identifier: BSD-3-Clause

from datawidgets import DataColumn, DataTable, LinkColumn
from storagelib import storageDB
from xmlgen import xhtml

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

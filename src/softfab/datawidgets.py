# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from typing import ClassVar, Iterator, Optional, Sequence, Union, cast

from softfab.databaselib import Database
from softfab.pageargs import ArgsCorrected
from softfab.querylib import KeySorter, runQuery
from softfab.timeview import formatDuration, formatTime
from softfab.utils import abstract, escapeURL, pluralize
from softfab.webgui import Column, Table, cell, pageLink, pageURL, row
from softfab.xmlgen import xhtml


class DataColumn(Column):
    label = None # type: Optional[str]
    keyName = None # type: Optional[str]
    sortKey = None # type: Union[None, str, staticmethod]
    '''Can be used to override the comparison key for sorting, using either
    the name of a record item or a static method that, when called with
    a record, returns the comparison key.
    '''

    def __init__(self, label = None, keyName = None, **kwargs):
        if keyName is None:
            keyName = self.keyName
        if label is None:
            if self.label is None:
                if keyName is not None:
                    label = keyName.capitalize()
            else:
                label = self.label
        Column.__init__(self, label, **kwargs)
        if keyName is not None:
            # Override class-scope default.
            self.keyName = keyName

    def presentHeaderContent(self, proc, table, **kwargs):
        content = super().presentHeaderContent(proc=proc, **kwargs)

        # Is this a column with data attached?
        keyName = self.keyName
        if keyName is None:
            return content
        sortField = table.sortField
        if sortField is None or not proc.args.isArgument(sortField):
            return content

        # Determine index in current sort order and compute new sort order.
        sortOrder = list(getattr(proc.args, sortField))
        index = sortOrder.index(keyName)
        del sortOrder[index]
        sortOrder.insert(0, keyName)

        override = {sortField: sortOrder}
        tabOffsetField = table.tabOffsetField
        if tabOffsetField is not None:
            override[tabOffsetField] = 0
        return pageLink(proc.page.name, proc.args.override(**override))(
            class_='sortorder'
            )[
            content, ' ', xhtml.span(class_='sortorder')['%d' % (index + 1)]
            ]

    def presentCell(self, record, **kwargs): # pylint: disable=unused-argument
        return record[self.keyName]

class BoolDataColumn(DataColumn):

    def presentCell(self, record, **kwargs):
        value = record[self.keyName]
        if value is True:
            return 'yes'
        elif value is False:
            return '-'
        else:
            raise TypeError(
                '"%s" is of type "%s"; expected bool'
                % ( value, type(value).__name__ )
                )

class ListDataColumn(DataColumn):

    def presentCell(self, record, **kwargs):
        return ', '.join(record[self.keyName])

class LinkColumn(DataColumn):

    def __init__(self, label, page, idArg = 'id', extraArgs = (), **kwargs):
        DataColumn.__init__(self, label, **kwargs)
        self.__urlBase = (
            page + '?' +
            ''.join(
                '%s=%s&' % ( name, escapeURL(value) )
                for name, value in extraArgs
                ) +
            idArg + '='
            )

    def presentCell(self, record, **kwargs):
        return xhtml.a(href = self.__urlBase + escapeURL(record.getId()))[
            self.label
            ]

class TimeColumn(DataColumn):
    cellStyle = 'nobreak'
    keyDisplay = None

    def __init__(self,
        label = None, keyName = None, keyDisplay = None, **kwargs
        ):
        if keyDisplay is not None:
            # Override class-scope default.
            self.keyDisplay = keyDisplay
        assert self.keyDisplay is not None
        DataColumn.__init__(self, label, keyName, **kwargs)

    def presentCell(self, record, **kwargs):
        return formatTime(record[self.keyDisplay])

class DurationColumn(DataColumn):
    cellStyle = 'nobreak'

    def presentCell(self, record, **kwargs):
        return cell(class_ = 'rightalign')[formatDuration(record[self.keyName])]

class _TableData:

    def __init__(self, table, proc):
        columns = tuple(table.iterColumns(proc=proc, data=None))

        records = table.getRecordsToQuery(proc)
        if hasattr(records, '__len__'):
            unfilteredNrRecords = len(records)
        else:
            # We could store all records in a list or wrap a counting iterator
            # around it, but so far that has not been necessary.
            unfilteredNrRecords = None

        sortField = table.sortField
        if sortField is None:
            # We don't know if getRecordsToQuery() has filtered or not.
            filtered = None
        else:
            sortOrder = getattr(proc.args, sortField)
            cleanSortOrder = self.__cleanSortOrder(columns, sortOrder)
            if sortOrder != cleanSortOrder:
                if proc.args.isArgument(sortField):
                    raise ArgsCorrected(proc.args.override(
                        **{ sortField: cleanSortOrder }
                        ))
                else:
                    setattr(proc.args, sortField, cleanSortOrder)
            query = list(table.iterFilters(proc))
            filtered = bool(query)
            keyMap = _buildKeyMap(columns)
            query.append(KeySorter(
                (keyMap.get(key, key) for key in cleanSortOrder),
                table.db, table.uniqueKeys
                ))
            records = runQuery(query, records)

        totalNrRecords = len(records)
        tabOffsetField = table.tabOffsetField
        if tabOffsetField is not None:
            tabOffset = getattr(proc.args, tabOffsetField)
            recordsPerPage = table.recordsPerPage
            newOffset = tabOffset
            if tabOffset < 0:
                # User tried to be funny and entered negative offset in URL.
                # Clip to first tab.
                newOffset = 0
            elif tabOffset >= totalNrRecords:
                # URL could be manipulated or were are looking at a database
                # from which records were recently deleted.
                # Clip to last tab.
                newOffset = (totalNrRecords // recordsPerPage) * recordsPerPage
            else:
                # Make sure the first record on a tab matches the tab label.
                # Round down to current tab label.
                newOffset = (tabOffset // recordsPerPage) * recordsPerPage
            if newOffset != tabOffset:
                raise ArgsCorrected(proc.args.override(
                    **{ tabOffsetField: newOffset }
                    ))
            records = records[tabOffset : tabOffset + table.recordsPerPage]

        self.columns = columns
        self.records = records
        self.unfilteredNrRecords = unfilteredNrRecords
        self.totalNrRecords = totalNrRecords
        self.filtered = filtered

    def __cleanSortOrder(self, columns, sortOrder):
        '''Returns the given sort order, with non-existing column keys removed,
        duplicate keys removed and missing keys added.
        '''
        colKeys = [
            key for key in (column.keyName for column in columns)
            if key is not None
            ]

        cleanSortOrder = []
        # Add keys that exist and are not duplicates.
        for key in sortOrder:
            if key in colKeys and key not in cleanSortOrder:
                cleanSortOrder.append(key)
        # Add missing keys.
        for key in colKeys:
            if key not in cleanSortOrder:
                cleanSortOrder.append(key)
        return tuple(cleanSortOrder)

def _buildKeyMap(columns):
    '''Returns a mapping from column key name to a key name or key function
    used to retrieve the comparison key.
    '''
    keyMap = {}
    for column in columns:
        if isinstance(column, DataColumn):
            keyName = column.keyName
            if keyName is not None:
                sortKey = column.sortKey
                if sortKey is not None:
                    keyMap[keyName] = sortKey
    return keyMap

class DataTable(Table, ABC):
    '''A table filled with data from a database.
    '''
    # Database to fetch records from.
    # This field is allowed to be None if getRecordsToQuery() is overridden,
    # but specifying a Database object allows more efficient sorting.
    db = abstract # type: ClassVar[Optional[Database]]
    # Keys for which the value will be unique for each record.
    # If None, the unique keys from the database will be used,
    # unless 'db' is None as well.
    uniqueKeys = None # type: Optional[Sequence[str]]
    # Name of field in Arguments that contains the sort order for this table,
    # or None to not sort the table. We never want to show records in random
    # order, so if this field is None, getRecordsToQuery() must return already
    # sorted records.
    # It is possible to refer to a non-argument member of Arguments if you want
    # a fixed sort order.
    sortField = 'sort' # type: Optional[str]
    # Name of field in Arguments that contains the record number to show
    # in the current tab, or None to not use tabs.
    tabOffsetField = 'first' # type: Optional[str]
    # Maximum number of records to display at once.
    # Ignored if tabOffsetField is None.
    recordsPerPage = 100
    # Name of type (plural) of the records in this table. Used to display the
    # total record count. If None, it is based on "db.description".
    objectName = None # type: Optional[str]
    # Print total record count above this table?
    printRecordCount = True
    # Maximum number of tabs that can be put above a table.
    __maxNrTabs = 10

    def __init__(self):
        Table.__init__(self)
        if self.objectName is None:
            self.objectName = pluralize(self.db.description, 42)

    def getRecordsToQuery(self, proc): # pylint: disable=unused-argument
        '''Returns the initial record set on which filters will be applied.
        If "sortField" is None, the initial record set must be already sorted.
        '''
        return self.db

    def iterFilters(self, proc): # pylint: disable=unused-argument
        '''Generates filter objects (see "querylib" module) to filter the
        records that are going to be displayed in a DataTable.
        The default implementation yields no filters; override this method to
        apply filters.
        Note: Since filtering should be done before sorting and sorting is
              mandatory, DataTable will only call this method if it is
              responsible for sorting (sortField is not None).
        '''
        return ()

    def process(self, proc):
        '''Runs the queries necessary to populate the this table with data.
        Raises ArgsCorrected if the sort order was invalid or incomplete.
        '''
        return _TableData(self, proc)

    def iterColumns(self, **kwargs: object) -> Iterator[Column]:
        data = cast(Optional[_TableData], kwargs['data'])
        if data is None:
            return super().iterColumns(**kwargs)
        else:
            # Use cached version.
            return iter(data.columns)

    def iterRowStyles(self, rowNr, record, **kwargs): # pylint: disable=unused-argument
        '''Override this to apply one or more CSS styles to a row.
        '''
        return ()

    def iterRows(self, *, data, **kwargs):
        columns = data.columns
        for rowNr, record in enumerate(data.records):
            style = self.joinStyles(
                self.iterRowStyles(rowNr, record, data=data, **kwargs)
                )
            yield row(class_ = style)[(
                column.presentCell(record, data=data, **kwargs)
                for column in columns
                )]

    def __presentNrRecords(self, data):
        '''Generate a piece of text displaying the total record count.
        '''
        if not self.printRecordCount:
            # Table subclass declares it does not want record count.
            return None

        originalNrRecords = (
            data.unfilteredNrRecords if self.db is None else len(self.db)
            )
        # Note: None (unknown) is treated the same as False (not filtered).
        if data.filtered and originalNrRecords is not None:
            return 'Number of %s matching: %d of %d' % (
                self.objectName,
                data.totalNrRecords,
                originalNrRecords
                )
        else:
            return 'Number of %s found: %d' % (
                self.objectName,
                data.totalNrRecords
                )

    def __showTabs(self, data):
        '''Returns True iff this table should be presented with tabs.
        '''
        if self.tabOffsetField is None:
            # Table subclass declares it does not want tabs.
            return False

        # Is there more than 1 tab worth of data?
        return data.totalNrRecords > self.recordsPerPage

    def __presentTabs(self, proc, data):
        '''Generate tabs to switch pages of a long record set.
        '''
        if not self.__showTabs(data):
            return None

        numColumns = sum(column.colSpan for column in data.columns)
        totalNrRecords = data.totalNrRecords
        recordsPerPage = self.recordsPerPage
        tabOffsetField = self.tabOffsetField
        current = getattr(proc.args, tabOffsetField)
        maxNrTabs = self.__maxNrTabs
        numDigits = len(str(totalNrRecords))
        numTabs = (totalNrRecords + recordsPerPage - 1) // recordsPerPage
        firstTab = max(current // recordsPerPage - maxNrTabs // 2, 0)
        limitTab = min(numTabs, firstTab + maxNrTabs)

        def linkTab(tab, text):
            return xhtml.td(class_ = 'navother')[
                xhtml.a(
                    href = pageURL(
                        proc.page.name,
                        proc.args.override(
                            **{tabOffsetField: tab * recordsPerPage}
                            )
                        ),
                    class_ = 'nav'
                    )[ text ]
                ]

        def pageTab(tab):
            pageFirst = tab * recordsPerPage
            pageLast = min(pageFirst + recordsPerPage - 1, totalNrRecords - 1)
            text = str(pageFirst).zfill(numDigits)
            if pageFirst <= current <= pageLast:
                return xhtml.td(class_ = 'navthis')[ text ]
            else:
                return linkTab(tab, text)

        return xhtml.tr[ xhtml.td(class_ = 'topnav', colspan = numColumns)[
            xhtml.table(class_ = 'topnav')[
                xhtml.tbody[
                    xhtml.tr[
                        linkTab(max(firstTab - maxNrTabs // 2, 0), '\u2190')
                            if firstTab > 0 else None,
                        ( pageTab(tab) for tab in range(firstTab, limitTab) ),
                        linkTab(min(
                            firstTab + maxNrTabs + maxNrTabs // 2, numTabs - 1
                            ), '\u2192')
                            if numTabs > limitTab else None
                        ]
                    ]
                ]
            ] ]

    def present(self, *, proc, **kwargs):
        data = proc.getTableData(self)
        return super().present(proc=proc, data=data, table=self, **kwargs)

    def presentCaptionParts(self, *, data, **kwargs):
        yield self.__presentNrRecords(data)

    def presentHeadParts(self, *, proc, data, **kwargs):
        yield self.__presentTabs(proc, data)
        yield super().presentHeadParts(proc=proc, data=data, **kwargs)

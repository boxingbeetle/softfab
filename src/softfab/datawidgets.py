# SPDX-License-Identifier: BSD-3-Clause

from collections.abc import Sized as SizedABC
from typing import (
    TYPE_CHECKING, Any, ClassVar, Dict, Generic, Iterable, Iterator, List,
    Mapping, Optional, Sequence, Tuple, Union, cast
)

from softfab.databaselib import DBRecord, Database, Retriever
from softfab.pageargs import ArgsCorrected
from softfab.querylib import (
    KeySorter, Record, RecordFilter, RecordProcessor, runQuery
)
from softfab.timeview import formatDuration, formatTime
from softfab.utils import abstract, escapeURL, pluralize
from softfab.webgui import Column, Table, cell, pageLink, pageURL, row
from softfab.xmlgen import XMLContent, XMLNode, XMLSubscriptable, xhtml

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from softfab.Page import PageProcessor
else:
    PageProcessor = object


class DataColumn(Column, Generic[Record]):
    label: Optional[str] = None
    keyName: Optional[str] = None
    sortKey: Union[None, str, Retriever] = None
    '''Can be used to override the comparison key for sorting, using either
    the name of a record item or a static method that, when called with
    a record, returns the comparison key.
    '''

    def __init__(self,
                 label: Optional[str] = None,
                 keyName: Optional[str] = None,
                 **kwargs: Any
                 ):
        if keyName is None:
            keyName = self.keyName
        if label is None:
            if self.label is None:
                if keyName is not None:
                    label = keyName.capitalize()
            else:
                label = self.label
        super().__init__(label, **kwargs)
        if keyName is not None:
            # Override class-scope default.
            self.keyName = keyName

    def presentHeaderContent(self, **kwargs: object) -> XMLContent:
        table = cast(DataTable, kwargs.pop('table'))
        proc = cast(PageProcessor, kwargs['proc'])
        content = super().presentHeaderContent(**kwargs)

        # Is this a column with data attached?
        keyName = self.keyName
        if keyName is None:
            return content
        sortField = table.sortField
        if sortField is None or not proc.args.isArgument(sortField):
            return content

        # Determine index in current sort order and compute new sort order.
        sortOrder: List[str] = list(getattr(proc.args, sortField))
        index = sortOrder.index(keyName)
        del sortOrder[index]
        sortOrder.insert(0, keyName)

        override: Dict[str, object] = {sortField: sortOrder}
        tabOffsetField = table.tabOffsetField
        if tabOffsetField is not None:
            override[tabOffsetField] = 0
        return pageLink(proc.page.name, proc.args.override(**override))(
            class_='sortorder'
            )[
            content, ' ', xhtml.span(class_='sortorder')[f'{index + 1:d}']
            ]

    def presentCell(self, # pylint: disable=unused-argument
                    record: Record,
                    **kwargs: object
                    ) -> XMLContent:
        key = self.keyName
        assert key is not None
        return cast(XMLContent, record[key])

class BoolDataColumn(DataColumn[Record]):

    def presentCell(self, record: Record, **kwargs: object) -> XMLContent:
        key = self.keyName
        assert key is not None
        value = record[key]
        if value is True:
            return 'yes'
        elif value is False:
            return '-'
        else:
            raise TypeError(
                f'"{value}" is of type "{type(value).__name__}"; expected bool'
                )

class ListDataColumn(DataColumn[Record]):

    def presentCell(self, record: Record, **kwargs: object) -> XMLContent:
        key = self.keyName
        assert key is not None
        return ', '.join(cast(Iterable[str], record[key]))

class LinkColumn(DataColumn[DBRecord]):

    def __init__(self, label: str, page: str, *,
                 idArg: str = 'id',
                 extraArgs: Sequence[Tuple[str, str]] = (),
                 **kwargs: Any
                 ):
        super().__init__(label, **kwargs)
        extraArgsStr = ''.join(
            f'{name}={escapeURL(value)}&'
            for name, value in extraArgs
            )
        self.__urlBase = f'{page}?{extraArgsStr}{idArg}='

    def presentLink(self, # pylint: disable=unused-argument
                    record: DBRecord,
                    **kwargs: object
                    ) -> XMLSubscriptable:
        return xhtml.a(href = self.__urlBase + escapeURL(record.getId()))

    def presentCell(self, record: DBRecord, **kwargs: object) -> XMLContent:
        return self.presentLink(record, **kwargs)[ self.label ]

class TimeColumn(DataColumn[Record]):
    cellStyle = 'nobreak'
    keyDisplay: Optional[str] = None

    def __init__(self,
                 label: Optional[str] = None,
                 keyName: Optional[str] = None,
                 keyDisplay: Optional[str] = None,
                 **kwargs: Any
                 ):
        if keyDisplay is not None:
            # Override class-scope default.
            self.keyDisplay = keyDisplay
        assert self.keyDisplay is not None
        super().__init__(label, keyName, **kwargs)

    def presentCell(self, record: Record, **kwargs: object) -> XMLContent:
        key = self.keyDisplay
        assert key is not None
        return formatTime(cast(Optional[int], record[key]))

class DurationColumn(DataColumn[Record]):
    cellStyle = 'nobreak'

    def presentCell(self, record: Record, **kwargs: object) -> XMLContent:
        key = self.keyName
        assert key is not None
        return cell(class_ = 'rightalign')[
            formatDuration(cast(Optional[int], record[key]))
            ]

class TableData(Generic[Record]):

    def __init__(self, table: 'DataTable[Record]', proc: PageProcessor):
        super().__init__()

        columns = tuple(table.iterColumns(proc=proc, data=None))

        records = table.getRecordsToQuery(proc)
        if isinstance(records, SizedABC):
            unfilteredNrRecords: Optional[int] = len(records)
        else:
            # We could store all records in a list or wrap a counting iterator
            # around it, but so far that has not been necessary.
            unfilteredNrRecords = None

        sortField = table.sortField
        if sortField is None:
            # We don't know if getRecordsToQuery() has filtered or not.
            filtered = None
            if isinstance(records, list):
                records = cast(List[Record], records)
            else:
                records = list(records)
        else:
            sortOrder = cast(Sequence[str], getattr(proc.args, sortField))
            cleanSortOrder = self.__cleanSortOrder(columns, sortOrder)
            if sortOrder != cleanSortOrder:
                if proc.args.isArgument(sortField):
                    raise ArgsCorrected(proc.args.override(
                        **{ sortField: cleanSortOrder }
                        ))
                else:
                    setattr(proc.args, sortField, cleanSortOrder)
            query: List[RecordProcessor] = list(table.iterFilters(proc))
            filtered = bool(query)
            keyMap = _buildKeyMap(columns)
            sortKeys = (keyMap.get(key, key) for key in cleanSortOrder)
            # TODO: Maybe we should have a class (RecordCollection?) for
            #       records that are not DBRecords or to keep track of
            #       a subset of a full DB. Then 'uniqueKeys' could be moved
            #       from DataTable to RecordCollection.
            db = table.db
            if db is None:
                query.append(KeySorter.forCustom(sortKeys, table.uniqueKeys))
            else:
                assert table.uniqueKeys is None, "table's uniqueKeys is ignored"
                query.append(KeySorter.forDB(sortKeys, db))
            records = runQuery(query, records)

        totalNrRecords = len(records)
        tabOffsetField = table.tabOffsetField
        if tabOffsetField is not None:
            tabOffset: int = getattr(proc.args, tabOffsetField)
            recordsPerPage = table.recordsPerPage
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

    def __cleanSortOrder(self,
                         columns: Sequence[DataColumn[Record]],
                         sortOrder: Sequence[str]
                         ) -> Sequence[str]:
        '''Returns the given sort order, with non-existing column keys removed,
        duplicate keys removed and missing keys added.
        '''
        colKeys = [
            key for key in (column.keyName for column in columns)
            if key is not None
            ]

        cleanSortOrder: List[str] = []
        # Add keys that exist and are not duplicates.
        for key in sortOrder:
            if key in colKeys and key not in cleanSortOrder:
                cleanSortOrder.append(key)
        # Add missing keys.
        for key in colKeys:
            if key not in cleanSortOrder:
                cleanSortOrder.append(key)
        return tuple(cleanSortOrder)

def _buildKeyMap(columns: Iterable[DataColumn[Record]]
                 ) -> Mapping[str, Union[str, Retriever]]:
    '''Returns a mapping from column key name to a key name or key function
    used to retrieve the comparison key.
    '''
    keyMap = {}
    for column in columns:
        keyName = column.keyName
        if keyName is not None:
            sortKey = column.sortKey
            if sortKey is not None:
                keyMap[keyName] = sortKey
    return keyMap

class DataTable(Table, Generic[Record]):
    '''A table filled with data from a database.
    '''
    # Database to fetch records from.
    # This field is allowed to be None if getRecordsToQuery() is overridden,
    # but specifying a Database object allows more efficient sorting.
    db: ClassVar[Optional[Database]] = abstract
    # Keys for which the value will be unique for each record.
    # If None, the unique keys from the database will be used,
    # unless 'db' is None as well.
    uniqueKeys: Optional[Sequence[str]] = None
    # Name of field in Arguments that contains the sort order for this table,
    # or None to not sort the table. We never want to show records in random
    # order, so if this field is None, getRecordsToQuery() must return already
    # sorted records.
    # It is possible to refer to a non-argument member of Arguments if you want
    # a fixed sort order.
    sortField: Optional[str] = 'sort'
    # Name of field in Arguments that contains the record number to show
    # in the current tab, or None to not use tabs.
    tabOffsetField: Optional[str] = 'first'
    # Maximum number of records to display at once.
    # Ignored if tabOffsetField is None.
    recordsPerPage = 100
    # Name of type (plural) of the records in this table. Used to display the
    # total record count. If None, it is based on "db.description".
    objectName: Optional[str] = None
    # Print total record count above this table?
    printRecordCount = True
    # Maximum number of tabs that can be put above a table.
    __maxNrTabs = 10

    def __init__(self) -> None:
        super().__init__()
        if self.objectName is None:
            assert self.db is not None
            self.objectName = pluralize(self.db.description, 42)

    def getRecordsToQuery(self, proc: PageProcessor) -> Iterable[Record]:
        '''Returns the initial record set on which filters will be applied.
        If "sortField" is None, the initial record set must be already sorted.
        '''
        db = self.db
        assert db is not None
        return db

    def iterFilters(self,
                    proc: PageProcessor
                    ) -> Iterator[RecordFilter[Record]]:
        '''Generates filter objects (see "querylib" module) to filter the
        records that are going to be displayed in a DataTable.
        The default implementation yields no filters; override this method to
        apply filters.
        Note: Since filtering should be done before sorting and sorting is
              mandatory, DataTable will only call this method if it is
              responsible for sorting (sortField is not None).
        '''
        return iter(())

    def process(self, proc: PageProcessor) -> TableData[Record]:
        '''Runs the queries necessary to populate the this table with data.
        Raises ArgsCorrected if the sort order was invalid or incomplete.
        '''
        return TableData(self, proc)

    def iterColumns(self, **kwargs: object) -> Iterator[DataColumn[Record]]:
        data = cast(Optional[TableData[Record]], kwargs['data'])
        if data is None:
            return cast(Iterator[DataColumn], super().iterColumns(**kwargs))
        else:
            # Use cached version.
            return iter(data.columns)

    def iterRowStyles(self,
                      rowNr: int,
                      record: Record,
                      **kwargs: object
                      ) -> Iterator[str]:
        '''Override this to apply one or more CSS styles to a row.
        '''
        return iter(())

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        data = cast(TableData[Record], kwargs['data'])
        columns = data.columns
        for rowNr, record in enumerate(data.records):
            style = self.joinStyles(
                self.iterRowStyles(rowNr, record, **kwargs)
                )
            yield row(class_ = style)[(
                column.presentCell(record, **kwargs)
                for column in columns
                )]

    def __presentNrRecords(self, data: TableData[Record]) -> XMLContent:
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
            return f'Number of {self.objectName} matching: ' \
                   f'{data.totalNrRecords:d} of {originalNrRecords:d}'
        else:
            return f'Number of {self.objectName} found: ' \
                   f'{data.totalNrRecords:d}'

    def __presentTabs(self,
                      proc: PageProcessor,
                      data: TableData[Record]
                      ) -> XMLContent:
        '''Generate tabs to switch pages of a long record set.
        '''

        # Should this table should be presented with tabs?
        tabOffsetField = self.tabOffsetField
        if tabOffsetField is None:
            # Table subclass declares it does not want tabs.
            return None

        # Is there more than 1 tab worth of data?
        recordsPerPage = self.recordsPerPage
        totalNrRecords = data.totalNrRecords
        if totalNrRecords <= recordsPerPage:
            return None

        numColumns = sum(column.colSpan for column in data.columns)
        current = cast(int, getattr(proc.args, tabOffsetField))
        maxNrTabs = self.__maxNrTabs
        numDigits = len(str(totalNrRecords))
        numTabs = (totalNrRecords + recordsPerPage - 1) // recordsPerPage
        firstTab = max(current // recordsPerPage - maxNrTabs // 2, 0)
        limitTab = min(numTabs, firstTab + maxNrTabs)

        def linkTab(tab: int, text: str) -> XMLNode:
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

        def pageTab(tab: int) -> XMLNode:
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

    def present(self, **kwargs: object) -> XMLContent:
        proc = cast(PageProcessor, kwargs['proc'])
        data = proc.getTableData(self)
        return super().present(data=data, table=self, **kwargs)

    def presentCaptionParts(self, **kwargs: object) -> XMLContent:
        data = cast(TableData[Record], kwargs['data'])
        yield self.__presentNrRecords(data)

    def presentHeadParts(self, **kwargs: object) -> XMLContent:
        proc = cast(PageProcessor, kwargs['proc'])
        data = cast(TableData[Record], kwargs['data'])
        yield self.__presentTabs(proc, data)
        yield super().presentHeadParts(**kwargs)

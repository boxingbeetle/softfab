# SPDX-License-Identifier: BSD-3-Clause

'''This module should evolve into an XHTML GUI toolkit.
TODO: Currently the "css" Python argument sets the XHTML "style" attribute and
      the "style" Python argument sets the XHTML "class" attribute.
      The fact that "style" does not map to "style" is confusing.
'''

from io import BytesIO
from itertools import chain
from typing import (
    Callable, ClassVar, Dict, Iterable, Iterator, List, Mapping, Optional,
    Sequence, Tuple, TypeVar, Union, cast
)
from xml.etree import ElementTree
import logging

from softfab.pageargs import PageArgs, Query
from softfab.pnglib import getPNGDimensions
from softfab.typing import NoReturn
from softfab.utils import SharedInstance, iterable
from softfab.xmlgen import (
    XML, XMLContent, XMLNode, XMLPresentable, XMLSubscriptable, adaptToXML,
    xhtml
)


def pageURL(
        page: str,
        args: Optional[PageArgs] = None,
        **kwargs: str
        ) -> str:
    '''Constructs URL of another page.
    '''
    # Note: Require the page name even when linking to the same page,
    #       since otherwise if the query is empty, the result will be
    #       an empty URL, which does not lead to a page fetch.
    assert page
    query = Query({}) if args is None else Query.fromArgs(args)
    query = query.override(**kwargs)
    return '%s?%s' % (page, query.toURL()) if query else page

def pageLink(
        page: str,
        args: Optional[PageArgs] = None,
        **kwargs: str
        ) -> XMLNode:
    '''Creates a hyperlink to another page.
    '''
    return xhtml.a(href=pageURL(page, args, **kwargs))

def maybeLink(url: Optional[str]) -> XMLSubscriptable:
    '''Creates a hyperlink if the URL is not None, otherwise returns the label
    as an XML tree.
    '''
    # Note: Use an "if" statement because mypy doesn't combine the types
    #       in the way we need when a conditional expression is used.
    #         https://github.com/python/mypy/issues/5392
    if url is None:
        return xhtml
    else:
        return xhtml.a(href = url)

def docLink(path: str) -> XMLNode:
    '''Creates a hyperlink to a documentation page.
    '''
    assert path.startswith('/'), path
    return xhtml.a(href='docs' + path, target='_blank')

def preserveSpaces(text: str) -> str:
    '''Replace all spaces in `text` by non-break space, such that the space
    characters will not be collapsed in HTML rendering.
    '''
    return text.replace(' ', '\u00A0')

class PresenterFunction:
    '''Wrapper that calls a function to present itself.
    TODO: If this is consistently useful, consider adding "call to present"
          as a feature of xmlgen.
    '''

    def __init__(self, func: Callable[..., XMLContent]):
        self._func = func

    def present(self, **kwargs: object) -> XMLContent:
        return self._func(**kwargs)

ContainerT = TypeVar('ContainerT', bound='Container')

class Container:
    '''A page element containing other page elements.
    '''

    def __init__(self, contents: Iterable[XMLPresentable]):
        self._contents = contents

    def _replaceContents(
            self: ContainerT, contents: Iterable[XMLPresentable]
            ) -> ContainerT:
        return self.__class__(contents)

    def _adaptContentElement(self, element: XMLContent
                             ) -> Iterator[XMLPresentable]:
        yield adaptToXML(element)

    def __getitem__(self: ContainerT, index: XMLContent) -> ContainerT:
        if iterable(index):
            newContents = cast(Iterable[XMLContent], index)
        else:
            newContents = (index,)
        return self._replaceContents(tuple(chain(
            self._contents, *(
                self._adaptContentElement(element)
                for element in newContents
                )
            )))

    def prepend(self: ContainerT, *content: XMLContent) -> ContainerT:
        '''Returns a new container with the given `content` prepended
        to the contents of this one.
        '''
        return self._replaceContents(tuple(chain(
            *(
                self._adaptContentElement(element)
                for element in content
                ),
            self._contents
            )))

    def append(self: ContainerT, *content: XMLContent) -> ContainerT:
        '''Returns a new container with the given `content` appended
        to the contents of this one.
        '''
        return self._replaceContents(tuple(chain(
            self._contents, *(
                self._adaptContentElement(element)
                for element in content
                )
            )))

    def _presentContents(self, **kwargs: object) -> Iterator[XMLContent]:
        for element in self._contents:
            yield element.present(**kwargs)

AttrContainerT = TypeVar('AttrContainerT', bound='AttrContainer')

class AttrContainer(Container):
    '''A container that can have attributes.
    '''

    def __init__(self, contents: Iterable[XMLPresentable],
                 attributes: Mapping[str, object]):
        super().__init__(contents)
        self._attributes = attributes

    def _replaceContents(
            self: AttrContainerT, contents: Iterable[XMLPresentable]
            ) -> AttrContainerT:
        return self.__class__(contents, self._attributes)

    def _replaceAttributes(
            self: AttrContainerT, attributes: Mapping[str, object]
            ) -> AttrContainerT:
        return self.__class__(self._contents, attributes)

    def __call__(self: AttrContainerT, **kwargs: object) -> AttrContainerT:
        attributes = dict(self._attributes)
        for key, value in kwargs.items():
            key = key.rstrip('_')
            if value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = value
        return self._replaceAttributes(attributes)

class _GroupItem(AttrContainer):
    '''Wraps an item that is contained within a group container.
    '''

    @staticmethod
    def adapt(obj: XMLContent) -> '_GroupItem':
        '''Returns `obj` if it is a group item, otherwise returns
        a new group item with `obj` as its contents.
        '''
        return obj if isinstance(obj, _GroupItem) else groupItem[obj]

    def present(self, *, tag: XMLNode, **kwargs: object) -> XMLContent:
        presentations = [
            presentation
            for presentation in self._presentContents(**kwargs)
            if presentation
            ]
        if presentations:
            return tag(**self._attributes)[presentations]
        else:
            return None

groupItem = _GroupItem((), {})

class _Group(AttrContainer):
    '''Container for `hgroup`, `vgroup` and `unorderedList`.
    '''
    groupTag = xhtml.div
    itemTag = xhtml.div

    def _adaptContentElement(self, element: XMLContent) -> Iterator[XML]:
        yield adaptToXML(cast(XMLPresentable, groupItem.adapt(element)))

    def present(self, **kwargs: object) -> XMLContent:
        itemTag = self.itemTag
        presentations = [
            presentation
            for presentation in self._presentContents(tag=itemTag, **kwargs)
            if presentation
            ]
        if presentations:
            return self.groupTag(**self._attributes)[ presentations ]
        else:
            return None

hgroup = _Group((), dict(class_ = 'hgroup'))
'''Container that groups page elements horizontally, aligned to top.
Items with an empty presentation will not have cells allocated to them.
If all items present empty, the group itself is omitted.
'''

vgroup = _Group((), dict(class_ = 'vgroup'))
'''Container that groups page elements vertically, with equal width.
Items with an empty presentation will not have cells allocated to them.
If all items present empty, the group itself is omitted.
'''

class _UnorderedList(_Group):
    groupTag = xhtml.ul
    itemTag = xhtml.li

unorderedList = _UnorderedList((), {})
'''Container that displays its items as an unordered (bullet) list.
Items with an empty presentation will be dropped from the list.
If all items present empty, the list itself is omitted.
'''

class _Decoration(Container):
    '''Offers a convenient way to decorate widgets which may be presented or
    hidden depending on the processing result.
    If one of the contained page elements has an empty presentation, the
    entire group is hidden. Otherwise, the entire group is presented.
    '''

    def present(self, **kwargs: object) -> XMLContent:
        presentations = []
        for presentation in self._presentContents(**kwargs):
            if not presentation:
                # Hide sequence.
                return None
            presentations.append(presentation)
        # Present sequence.
        return presentations

decoration = _Decoration(())

class Widget(XMLPresentable):
    '''GUI element.
    Provides a shared instance to its subclasses: "SomeWidget.instance".
    '''
    instance = SharedInstance() # type: ClassVar[SharedInstance]

    widgetId = None # type: Optional[str]
    '''Unique ID string that identifies this widget, or None.
    Corresponds to the "id" attribute in XML.
    '''
    autoUpdate = False
    '''Automatically update the presentation of this widget in pages using
    JavaScript? False by default.
    '''

    @staticmethod
    def joinStyles(styles: Iterable[str]) -> Optional[str]:
        '''Returns a single string containing all the given CSS styles separated
        by spaces, or None if there were no styles given.
        '''
        assert iterable(styles), type(styles)
        return ' '.join(styles) or None

    def present(self, **kwargs: object) -> XMLContent:
        '''Presents this widget in XHTML using data from the given processor.
        Returns an XML tree.
        '''
        raise NotImplementedError

class Column:
    instance = SharedInstance() # type: ClassVar[SharedInstance]

    label = None # type: XMLContent
    colSpan = 1
    cellStyle = None # type: Optional[str]

    @staticmethod
    def adapt(obj: Union['Column', XMLContent]) -> 'Column':
        '''Returns `obj` if it is a column, otherwise returns a new column
        with `obj` as its label.
        '''
        return obj if isinstance(obj, Column) else Column(obj)

    def __init__(self,
            label: XMLContent = None,
            colSpan: int = 1,
            cellStyle: Optional[str] = None
            ):
        if label is not None:
            self.label = label
        if colSpan != 1:
            self.colSpan = colSpan
        if cellStyle is not None:
            self.cellStyle = cellStyle

    def presentHeader(self, **kwargs: object) -> XMLNode: # pylint: disable=unused-argument
        """Presents the header tag without content."""
        colSpan = self.colSpan
        return xhtml.th(
            scope='col',
            colspan=None if colSpan == 1 else colSpan,
            class_=self.cellStyle
            )

    def presentHeaderContent(self, **kwargs: object) -> XMLContent: # pylint: disable=unused-argument
        """Presents the content for the header tag."""
        return self.label

class _Cell(AttrContainer):
    '''While our table rows accept cell content unwrapped, sometimes
    attributes such as `colspan` and `rowspan` need to be defined on
    the cell and that is what this wrapper is for.
    If `colspan` or `rowspan` is 0, the cell is omitted.
    If `colspan` or `rowspan` is 1, that attribute is removed.
    '''

    tag = xhtml.td

    @staticmethod
    def adapt(obj: XMLContent) -> '_Cell':
        '''Returns `obj` if it is a cell, otherwise returns a new cell
        with `obj` as its contents.
        '''
        return obj if isinstance(obj, _Cell) else cell[obj]

    def present(self, **kwargs: object) -> XMLContent:
        attributes = self._attributes
        colspan = attributes.get('colspan')
        rowspan = attributes.get('rowspan')
        if colspan == 0 or rowspan == 0:
            return None
        if colspan == 1 or rowspan == 1:
            attributes = dict(attributes)
            if colspan == 1:
                del attributes['colspan']
            if rowspan == 1:
                del attributes['rowspan']
        return self.tag(**attributes)[
            self._presentContents(**kwargs)
            ]

class _Header(_Cell):
    tag = xhtml.th

cell = _Cell((), {})
header = _Header((), {})

class _Row(AttrContainer):
    '''While our table accepts row content unwrapped, sometimes
    attributes such as `class` and `onclick` need to be defined on
    the row and that is what this wrapper is for.
    '''

    @staticmethod
    def adapt(obj: XMLContent) -> '_Row':
        '''Returns `obj` if it is a row, otherwise returns a new row
        with `obj` as its contents.
        '''
        return obj if isinstance(obj, _Row) else row[obj]

    def _adaptContentElement(self, element: XMLContent) -> Iterator[XML]:
        yield adaptToXML(cell.adapt(element))

    def present(self, **kwargs: object) -> XMLContent:
        colStyles = cast(Sequence[str], kwargs.pop('colStyles'))
        rowSpans = cast(List[int], kwargs.pop('rowSpans'))
        numCols = len(colStyles)
        assert len(rowSpans) == numCols

        def applyRowSpans(index: int) -> int:
            while index < numCols:
                rowspan = rowSpans[index]
                if rowspan == 1:
                    break
                elif rowspan > 1:
                    rowSpans[index] -= 1
                else:
                    # A rowspan of 0 means "until end of table" in HTML.
                    assert rowspan == 0
                index += 1
            return index

        cells = []
        index = 0
        for presented in self._presentContents(**kwargs):
            index = applyRowSpans(index)
            if presented:
                cellPresentation = cast(XMLNode, presented)
                attrs = cellPresentation.attrs
                rowspan = int(attrs.get('rowspan', '1'))
                if rowspan < 0:
                    raise ValueError(
                        'Illegal value %d for "rowspan" in column %d'
                        % (rowspan, index)
                        )
                colspan = int(attrs.get('colspan', '1'))
                if colspan < 1:
                    raise ValueError(
                        'Illegal value %d for "colspan" in column %d'
                        % (colspan, index)
                        )
                try:
                    for _ in range(colspan):
                        style = colStyles[index]
                        cellPresentation = cellPresentation.addClass(style)
                        if rowSpans[index] != 1:
                            raise ValueError(
                                'Overlapping row and column span in column %d'
                                % index
                                )
                        rowSpans[index] = rowspan
                        index += 1
                except IndexError as ex:
                    raise ValueError(
                        'Row cells extend past last column (%d)' % numCols
                        ) from ex
                cells.append(cellPresentation)
            index = applyRowSpans(index)

        if index != numCols:
            raise ValueError(
                'Table with %d columns contains row with %d cells' % (
                    numCols, index
                    )
                )

        return xhtml.tr(**self._attributes)[cells]

row = _Row((), {})

class Table(Widget):
    '''A generic abstract table.
    Subclass it to define the layout and provide contents.
    '''
    bodyId = None # type: Optional[str]
    style = None # type: Optional[str]
    hideWhenEmpty = False

    def present(self, **kwargs: object) -> XMLContent:
        # Any 'columns' argument will be from an outer table; discard it.
        kwargs.pop('columns', None)
        # Determine visible columns.
        columns = tuple(self.iterColumns(**kwargs))

        body = self.__presentBody(columns=columns, **kwargs)
        if body is None:
            return None
        else:
            return xhtml.table(
                id_ = self.widgetId,
                class_ = self.joinStyles(self.iterStyles(**kwargs))
                )[
                    self.__presentCaption(**kwargs),
                    self.__presentHead(columns=columns, **kwargs),
                    body
                ]

    def __presentCaption(self, **kwargs: object) -> XMLContent:
        presentations = adaptToXML(self.presentCaptionParts(**kwargs))
        return xhtml.caption[ presentations ] if presentations else None

    def presentCaptionParts(self, **kwargs: object) -> XMLContent: # pylint: disable=unused-argument
        return None

    def __presentHead(self,
            columns: Sequence[Column],
            **kwargs: object
            ) -> XMLContent:
        presentations = adaptToXML(
            self.presentHeadParts(columns=columns, **kwargs)
            )
        return xhtml.thead[ presentations ] if presentations else None

    def presentHeadParts(self, **kwargs: object) -> XMLContent:
        yield self.presentColumnHeads(**kwargs)

    def presentColumnHeads(self, **kwargs: object) -> XMLContent:
        columns = cast(Sequence[Column], kwargs['columns'])
        allNone = True
        columnPresentations = []
        for column in columns:
            headerTag = column.presentHeader(**kwargs)
            headerContent = column.presentHeaderContent(**kwargs)
            if headerContent is None:
                headerContent = ''
            else:
                allNone = False
            columnPresentations.append(headerTag[headerContent])
        if allNone:
            return None
        else:
            return xhtml.tr[ columnPresentations ]

    def __presentBody(self,
            columns: Sequence[Column],
            **kwargs: object
            ) -> XMLContent:
        # Determine style implied by each column.
        colStyles = []
        for column in columns:
            colStyle = column.cellStyle
            for _ in range(column.colSpan):
                colStyles.append(colStyle)

        rowSpans = [1] * len(colStyles)
        rowPresentations = [
            row.adapt(r).present(
                colStyles=colStyles, rowSpans=rowSpans, columns=columns,
                **kwargs
                )
            for r in self.iterRows(columns=columns, **kwargs)
            ] # type: XMLContent
        if max(rowSpans) > 1:
            raise ValueError(
                'Row span beyond last row: %s' % ', '.join(
                    '%s row(s) left in column %d' % (span - 1, index)
                    for index, span in enumerate(rowSpans)
                    if span > 1
                    )
                )
        if not rowPresentations:
            if self.hideWhenEmpty:
                return None
            else:
                rowPresentations = xhtml.tr[
                    xhtml.td(colspan = len(colStyles))[ '(no content)' ]
                    ]

        return xhtml.tbody(id = self.bodyId)[ rowPresentations ]

    def iterStyles(self, **kwargs: object) -> Iterator[str]: # pylint: disable=unused-argument
        '''Iterates through CSS classes for this table.
        The default implementation yields the "style" field unless it is None.
        '''
        style = self.style
        if style is not None:
            yield style

    def iterColumns(self, # pylint: disable=unused-argument
            **kwargs: object
            ) -> Iterator[Column]:
        '''Iterates through the column definitions.
        The default implementation iterates through the field named `columns`;
        each element in the field should be a Column instance or a string or
        XMLNode containing a column label.
        If the column should not be given a header, None should be used as the
        label; if all labels are None, the table will have no header.
        '''
        for column in getattr(self, 'columns'):
            yield Column.adapt(column)

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        '''Iterates through the row data.
        Each element should be a Row instance or an iterator through
        the cells in the row, where a cell is a Cell instance or a string
        or an XMLNode.
        '''
        raise NotImplementedError

class Panel(Table):
    '''A single-cell table.
    The panel is not presented if the content is empty.
    Subclasses should override either `content` or `presentContent()`.
    '''
    label = None # type: Optional[str]
    content = None # type: Optional[XMLPresentable]
    hideWhenEmpty = True

    def iterColumns(self, **kwargs: object) -> Iterator[Column]:
        yield Column.adapt(self.label)

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        content = adaptToXML(self.presentContent(**kwargs))
        if content:
            yield (content, )

    def presentContent(self, **kwargs: object) -> XMLContent:
        '''Presents the content of the panel's only cell.
        The default implementation presents our `content` attribute.
        '''
        return cast(XMLPresentable, self.content).present(**kwargs)

class PropertiesTable(Table):
    '''A common table type which shows one key-value pair per row.
    '''
    columns = 'Property', 'Value'
    style = 'properties'

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        # This method is already declared abstract in Table, we re-assert
        # that here to please PyLint.
        raise NotImplementedError

class Image(AttrContainer):

    @classmethod
    def create(cls,
               fileName: str,
               width: Optional[int] = None,
               height: Optional[int] = None
               ) -> 'Image':
        attributes = dict(alt='') # type: Dict[str, object]
        if width is not None:
            attributes['width'] = width
        if height is not None:
            attributes['height'] = height
        return cls(fileName, attributes)

    def __init__(self, fileName: str, attributes: Mapping[str, object]):
        super().__init__((), attributes)
        self.fileName = fileName

    def _replaceContents(self, contents: Iterable[XMLPresentable]) -> NoReturn:
        raise ValueError('Image does not support nested content')

    def _replaceAttributes(self, attributes: Mapping[str, object]) -> 'Image':
        return self.__class__(self.fileName, attributes)

    def present(self, **kwargs: object) -> XMLContent: # pylint: disable=unused-argument
        styleURL = cast(str, kwargs['styleURL'])
        url = '%s/%s' % (styleURL, self.fileName)
        return xhtml.img(src=url, **self._attributes)

def pngIcon(fileName: str, data: Optional[bytes]) -> Image:
    width, height = None, None
    if data is not None:
        with BytesIO(data) as inp:
            try:
                width, height = getPNGDimensions(inp)
            except ValueError as ex:
                logging.error(
                    'Invalid PNG file for icon "%s": %s', fileName, ex
                    )
    return Image.create(fileName, width, height)

def svgIcon(fileName: str, data: Optional[bytes]) -> Image:
    width = height = None
    if data is not None:
        try:
            svgElement = ElementTree.fromstring(data)
        except ElementTree.ParseError as ex:
            logging.error('Error parsing SVG icon "%s": %s', fileName, ex)
        else:
            widthStr = svgElement.get('width')
            width = None if widthStr is None else int(widthStr)
            heightStr = svgElement.get('height')
            height = None if heightStr is None else int(heightStr)
    return Image.create(fileName, width, height)

class ShortcutIcon(Widget):

    def __init__(self, name: str):
        Widget.__init__(self)
        self.__name = name

    def iterFiles(self) -> Iterator[Tuple[str, str]]:
        '''Iterates through pairs of file name and media type.
        '''
        yield self.__name + '.png', 'image/png'

    def present(self, **kwargs: object) -> XMLContent:
        '''Returns an XHTML fragment for using this icon as a shortcut icon.
        A shortcut icon is the small icon typically displayed to the left of
        the URL of a page in a web browser.
        '''
        styleURL = cast(str, kwargs['styleURL'])
        for fileName, mediaType in self.iterFiles():
            yield xhtml.link(
                rel = 'icon',
                href = '%s/%s' % (styleURL, fileName),
                type = mediaType,
                )

class StyleSheet(Widget):

    def __init__(self, fileName: str):
        Widget.__init__(self)
        self.fileName = fileName

    def present(self, **kwargs: object) -> XMLContent:
        '''Returns an XHTML fragment for linking this style sheet.
        '''
        styleURL = cast(str, kwargs['styleURL'])
        yield xhtml.link(
            rel = 'stylesheet',
            href = '%s/%s' % (styleURL, self.fileName),
            type = 'text/css',
            )

class Script(Widget):

    def present(self, **kwargs: object) -> XMLContent:
        body = '\n'.join(line for line in self.iterLines(**kwargs))
        return xhtml.script['\n%s\n' % body] if body else None

    def iterLines(self, **kwargs: object) -> Iterator[str]:
        raise NotImplementedError

class _ScriptContainer(AttrContainer):

    def present(self, **kwargs: object) -> XMLContent:
        presentations = [
            presentation
            for presentation in self._presentContents(**kwargs)
            if presentation
            ]
        if presentations:
            return xhtml.script(**self._attributes)[presentations]
        else:
            return None

script = _ScriptContainer((), {})

rowManagerScript = script[
r'''
// Constructor function for RowManager class.
function RowManager(bodyId, rowStart) {
    // The table body node.
    this.bodyNode = document.getElementById(bodyId);
    // The rows in this table.
    // There may be nested tables, but we only want top-level rows.
    this.rows = new Array(0);
    for (var i = 0; i < this.bodyNode.childNodes.length; i++) {
        var child = this.bodyNode.childNodes[i];
        if (child.nodeName == "tr" || child.nodeName == "TR") {
            this.rows.push(child);
        }
    }
    // Flags that indicate if the corresponding row is considered empty.
    this.emptyFlags = [];

    // Assume the last row is empty and save it for later duplication.
    this.template = this.rows[this.rows.length - 1].cloneNode(true);
    // Initialise rows that should be monitored.
    for (var index = rowStart; index < this.rows.length; index++) {
        this.initRow(this.rows[index], index);
    }
}

// Calls a visitor function for every edit element in the given row.
// The order in which the edit elements are passed is not specified.
function visitRow(rowNode, visitor) {
    var selectNodes = rowNode.getElementsByTagName('select');
    for (var i = 0; i < selectNodes.length; i++) {
        visitor(selectNodes[i]);
    }
    var inputNodes = rowNode.getElementsByTagName('input');
    for (var i = 0; i < inputNodes.length; i++) {
        var node = inputNodes[i];
        if (node.type == 'text' || node.type == 'checkbox') {
            visitor(node);
        }
    }
}

// Initialise administration and event handling for a new table row.
function initRow(node, index) {
    // Register event handler.
    var owner = this;
    visitRow(node, function(item) {
        item.onchange = function(event) { owner.rowChanged(index) }
        } );

    // Custom initialisation routine.
    if (this.initRowCustom != undefined) this.initRowCustom(node, index);

    // Is the new row empty? Typically, it will be.
    var empty = this.isEmptyRow(node);
    this.emptyFlags[index] = empty;
    if (empty) this.emptyCount++;
}

// Determines whether a row is empty.
function isEmptyRow(rowNode) {
    var selectNodes = rowNode.getElementsByTagName('select');
    for (var i = 0; i < selectNodes.length; i++) {
        // Note: We use here item[item.selectedIndex].value rather than
        //       item.value, because the latter does not work on all browsers.
        var item = selectNodes[i];
        if (item[item.selectedIndex].value != '') {
            return false;
        }
    }
    var inputNodes = rowNode.getElementsByTagName('input');
    for (var i = 0; i < inputNodes.length; i++) {
        var node = inputNodes[i];
        if ( (node.type == 'text' && node.value)
          || (node.type == 'checkbox' && node.checked)
          || (node.type == 'hidden') ) {
            return false;
        }
    }
    return inputNodes.length != 0;
}

// If there are no empty rows then add one by copying the empty template row.
function checkRows() {
    if (this.emptyCount <= 0) {
        var node = this.template.cloneNode(true);
        this.bodyNode.appendChild(node);
        this.rows.push(node);
        this.initRow(node, node.sectionRowIndex);
        // Even if the new row is not actually empty, consider it empty
        // to avoid adding lots of new rows.
        this.emptyCount = 1;
    }
}

// Update empty row administration for the given row.
function checkRow(index) {
    var curr = this.isEmptyRow(this.rows[index]);
    var prev = this.emptyFlags[index];
    this.emptyFlags[index] = curr;
    if (curr && !prev) {
        // Row has become empty.
        this.emptyCount++;
    } else if (!curr && prev) {
        // Row has become used.
        this.emptyCount -= 1;
    }
}

// Update administration for a changed row.
function rowChanged(index) {
    this.checkRow(index);
    this.checkRows();
}

// Define properties that will be automatically added to each instance.
// NOTE: Objects are not duplicated, but references are copied instead.
RowManager.prototype.emptyCount = 0;
RowManager.prototype.initRow = initRow;
RowManager.prototype.checkRow = checkRow;
RowManager.prototype.checkRows = checkRows;
RowManager.prototype.isEmptyRow = isEmptyRow;
RowManager.prototype.rowChanged = rowChanged;
''']

class _RowManagerInstanceScript(AttrContainer):

    def _replaceContents(self, contents: Iterable[XMLPresentable]) -> NoReturn:
        raise ValueError(
            '"rowManagerInstanceScript" does not support nested content'
            )

    def present(self, **kwargs: object) -> XMLContent: # pylint: disable=unused-argument
        attributes = self._attributes

        bodyId = cast(str, attributes['bodyId'])
        rowStart = cast(int, attributes['rowStart'])
        lines = [
            "var rowManager = new RowManager('%s', %d);" % (bodyId, rowStart),
            'document.rowManager = rowManager;'
            ]

        initRowFunc = attributes.get('initRow')
        if initRowFunc:
            lines.append('rowManager.initRowCustom = %s;' % initRowFunc)

        return xhtml.script['\n'.join(lines)]

rowManagerInstanceScript = _RowManagerInstanceScript((), dict(rowStart=0))
'''JavaScript fragment to instantiate RowManagers.
Once RowManager has been instantiated for a given table it starts
functioning automatically, no other initialization is necessary.
'''

addRemoveStyleScript = script[r'''
function addStyle(node, style) {
    node.className += " " + style;
}
function removeStyle(node, style) {
    var styles = node.className.split(" ");
    var newStyleStr = "";
    for (var i = 0; i < styles.length; i++) {
        var oldStyle = styles[i];
        if (oldStyle != style) {
            if (newStyleStr != "") {
                newStyleStr += " ";
            }
            newStyleStr += oldStyle;
        }
    }
    node.className = newStyleStr;
}
''']

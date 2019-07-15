# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import (
    Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, cast
)
import logging
import sys

from markdown import Markdown
from markdown.extensions import Extension
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.def_list import DefListExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.treeprocessors import Treeprocessor
from markdown.util import etree
from twisted.python.urlpath import URLPath
from twisted.web.http import Request as TwistedRequest
from twisted.web.resource import Resource
from twisted.web.static import Data
from twisted.web.util import redirectTo

from softfab.FabPage import BasePage, LinkBarButton
from softfab.Page import Authenticator, PageProcessor, Responder
from softfab.StyleResources import styleRoot
from softfab.UIPage import UIResponder
from softfab.authentication import LoginAuthPage
from softfab.compat import importlib_resources
from softfab.pageargs import PageArgs
from softfab.render import renderAuthenticated
from softfab.response import Response
from softfab.userlib import User
from softfab.webgui import StyleSheet
from softfab.xmlgen import XML, XMLContent, XMLPresentable, parseHTML, xhtml

# Register pygments style sheet.
try:
    from pygments.formatters import HtmlFormatter
except ImportError:
    logging.warning(
        "The pygments package is not installed; "
        "code examples in the documentation will lack syntax highlighting"
        )
    pygmentsSheet = xhtml[None] # type: XMLPresentable
else:
    pygmentsFileName = 'pygments.css'
    styleRoot.putChild(
        pygmentsFileName.encode(),
        Data(
            HtmlFormatter().get_style_defs('.codehilite').encode(),
            'text/css'
            )
        )
    pygmentsSheet = StyleSheet(pygmentsFileName)

PI_Handler = Callable[[str], XMLContent]

def piHandlerDict(module: ModuleType) -> Dict[str, PI_Handler]:
    handlers = getattr(module, '__piHandlers', None)
    if handlers is None:
        handlers = {}
        setattr(module, '__piHandlers', handlers)
    return handlers

def piHandler(handler: PI_Handler) -> PI_Handler:
    """Decorator that marks a function as a processing instruction handler.
    Marked functions will be called for processing instructions where the
    target matches the function name.
    """

    module = sys.modules[handler.__module__]
    piHandlerDict(module)[handler.__name__] = handler
    return handler

class ExtractedInfo:
    """Fragments extracted from a documentation page."""

    def __init__(self, title: str, abstract: XML):
        self.title = title
        self.abstract = abstract

extractionFailedInfo = ExtractedInfo('Error', xhtml.p(class_='notice')['Error'])

class ExtractionProcessor(Treeprocessor):

    def run(self, root: etree.Element) -> None:
        # pylint: disable=attribute-defined-outside-init

        # Extract title from level 1 header.
        titleElem = root.find('./h1')
        title = titleElem.text
        root.remove(titleElem)

        # Extract first paragraph to use as an abstract.
        abstractElem = root[0]
        assert abstractElem.tag == 'p', abstractElem.tag
        abstractElem.tag = 'dd'
        abstract = xhtml[abstractElem]
        abstractElem.tag = 'p'
        abstractElem.set('class', 'abstract')

        self.extracted = ExtractedInfo(title, abstract)

class ExtractionExtension(Extension):
    """Extracts title and abstract."""

    @property
    def extracted(self) -> ExtractedInfo:
        return self.__processor.extracted

    def reset(self) -> None:
        self.__processor.extracted = extractionFailedInfo

    def extendMarkdown(self, md: Markdown) -> None:
        md.registerExtension(self)
        processor = ExtractionProcessor(md)
        md.treeprocessors.register(processor, 'softfab.extract', 0)
        # pylint: disable=attribute-defined-outside-init
        self.__processor = processor

class FixupProcessor(Treeprocessor):

    def fixAlign(self, cell: etree.Element) -> None:
        alignment = cell.attrib.pop('align')
        cell.set('style', 'text-align: ' + alignment)

    def run(self, root: etree.Element) -> None:
        for cell in root.findall('.//th[@align]'):
            self.fixAlign(cell)
        for cell in root.findall('.//td[@align]'):
            self.fixAlign(cell)

class FixupExtension(Extension):
    """Corrects invalid HTML5."""

    def extendMarkdown(self, md: Markdown) -> None:
        processor = FixupProcessor(md)
        md.treeprocessors.register(processor, 'softfab.fixup', 5)

# TODO: In Python 3.6, we could use IntFlag instead.
class DocErrors(Enum):
    """Errors that can happen when processing documentation.
    """

    MODULE = 1
    """Python module failed to load."""

    METADATA = 2
    """Missing metadata."""

    CONTENT = 3
    """Markdown content failed to load."""

    RENDERING = 4
    """Markdown content failed to render."""

class DocMetadata:
    button = 'ERROR'
    children = () # type: Sequence[str]
    icon = 'IconDocs'

class DocPage(BasePage['DocPage.Processor', 'DocPage.Arguments']):
    authenticator = LoginAuthPage.instance # type: Authenticator

    class Arguments(PageArgs):
        pass

    class Processor(PageProcessor[Arguments]):
        pass

    def __init__(self,
                 resource: 'DocResource',
                 module: Optional[ModuleType],
                 metadata: DocMetadata,
                 errors: Iterable[DocErrors]
                 ):
        super().__init__()
        self.resource = resource
        self.module = module
        self.metadata = metadata
        self.errors = set(errors)

        contentPath = None
        if module is not None:
            moduleFile = getattr(module, '__file__', None) # type: Optional[str]
            if moduleFile is not None:
                contentPath = Path(moduleFile).parent / 'contents.md'
        self.contentPath = contentPath

        self.contentMTime = None # type: Optional[int]
        self.__extractedInfo = None # type: Optional[ExtractedInfo]
        self.__renderedStr = None # type: Optional[str]
        self.__renderedXML = None # type: Optional[XML]
        self.__toc = () # type: Sequence[Tuple[str, ExtractedInfo]]

    def getMTime(self, path: Path) -> Optional[int]:
        """Returns the modification time of a source file,
        or None if that time could not be determined.
        """
        try:
            stats = path.stat()
        except OSError:
            # This happens when we're running from a ZIP.
            return None
        else:
            return stats.st_mtime_ns

    def checkModified(self) -> None:
        """Check whether source was modified, discard cached info if it was.
        """
        contentPath = self.contentPath
        if contentPath is None:
            return
        contentMTime = self.getMTime(contentPath)
        if contentMTime != self.contentMTime:
            self.contentMTime = contentMTime
            self.__renderedStr = None
            self.__renderedXML = None
            self.__extractedInfo = None
            self.errors.discard(DocErrors.CONTENT)
            self.errors.discard(DocErrors.RENDERING)

    def renderContent(self) -> None:
        self.checkModified()

        if self.__renderedStr is not None:
            # Previous render is still valid.
            return
        if DocErrors.CONTENT in self.errors:
            # Loading failed; nothing to render.
            return
        if DocErrors.RENDERING in self.errors:
            # Rendering attempted and failed.
            return

        # Load content.
        contentPath = self.contentPath
        if contentPath is None:
            # If the init module fails to import, resources in the package
            # are inaccessible. Don't try to load them, to avoid error spam.
            return
        packageName = self.resource.packageName
        try:
            content = importlib_resources.read_text(packageName,
                                                    contentPath.name)
        except Exception:
            logging.exception('Error loading documentation content "%s"',
                              contentPath.name)
            self.errors.add(DocErrors.CONTENT)
            return

        # Create a private Markdown converter.
        # Rendering a the table of content will trigger Markdown conversion
        # of child pages, so we can't use a single shared instance.
        extractor = ExtractionExtension()
        md = Markdown(
            extensions=[
                extractor,
                FixupExtension(),
                DefListExtension(),
                FencedCodeExtension(),
                CodeHiliteExtension(guess_lang=False),
                TableExtension()
                ]
            )

        # Do the actual rendering.
        try:
            self.__renderedStr = md.convert(content)
        except Exception:
            logging.exception('Error rendering Markdown for %s', packageName)
            self.errors.add(DocErrors.RENDERING)
        else:
            self.__extractedInfo = extractor.extracted

    def postProcess(self) -> Optional[XML]:
        """Returns a post-processed version of previously rendered content,
        or None if no rendered content is available or post-processing failed.
        """

        # Check whether table of contents needs updating.
        toc = tuple(
            (name + '/', page.extracted)
            for name, page in self.childPages
            )
        # Note that ExtractedInfo doesn't define __eq__, but since it is
        # cached, comparing object identity is good enough.
        if toc != self.__toc:
            self.__toc = toc
            self.__renderedXML = None

        # Use cached version if available.
        renderedXML = self.__renderedXML
        if renderedXML is not None:
            return renderedXML

        # Check whether we can post-process.
        module = self.module
        if module is None:
            return None
        renderedStr = self.__renderedStr
        if renderedStr is None:
            return None

        # While Python-Markdown uses ElementTree internally, there is
        # no way to get the full output as a tree, since inline HTML
        # is re-inserted after the tree has been serialized.
        # So unfortunately we have to parse the serialized output.
        try:
            renderedXML = parseHTML(
                renderedStr,
                piHandlers=piHandlerDict(module)
                )
        except Exception:
            logging.exception(
                'Error post-processing content for %s',
                self.resource.packageName
                )
            self.errors.add(DocErrors.RENDERING)
            return None
        else:
            self.__renderedXML = renderedXML
            return renderedXML

    @property
    def extracted(self) -> ExtractedInfo:
        self.renderContent()
        return self.__extractedInfo or extractionFailedInfo

    @property
    def childPages(self) -> Iterator[Tuple[str, 'DocPage']]:
        resource = self.resource
        for childName in self.metadata.children:
            childResource = resource.children[childName.encode()]
            yield childName, childResource.page

    def renderTableOfContents(self, arg: str) -> XMLContent:
        if arg:
            raise ValueError('"toc" does not take any arguments')

        yield xhtml.h2['Table of Contents']
        yield xhtml.dl(class_='toc')[(
            ( xhtml.dt[xhtml.a(href=url)[extracted.title]],
              extracted.abstract )
            for url, extracted in self.__toc
            )]

    def getResponder(self,
                     path: Optional[str],
                     proc: PageProcessor
                     ) -> Responder:
        self.renderContent()
        setattr(proc, 'content', self.postProcess())
        if self.errors:
            message = xhtml.p(class_='notice')[
                'Error in documentation ', xhtml[', '].join(self.errors), '. ',
                xhtml.br,
                'Please check the Control Center log for details.'
                ]
            return DocErrorResponder(
                self, cast('DocPage.Processor', proc), message
                )
        else:
            return super().getResponder(path, proc)

    def checkAccess(self, user: User) -> None:
        pass

    def presentHeadParts(self, **kwargs: object) -> XMLContent:
        yield pygmentsSheet.present(**kwargs)
        yield super().presentHeadParts(**kwargs)

    def pageTitle(self, proc: Processor) -> str:
        return (self.__extractedInfo or extractionFailedInfo).title

    def createLinkBarButton(self, url: str) -> LinkBarButton:
        return LinkBarButton(
            label=self.metadata.button,
            url=url,
            icon=styleRoot.addIcon(self.metadata.icon),
            active=not url
            )

    def iterRootButtons(self,
                        args: Optional[Arguments]
                        ) -> Iterator[LinkBarButton]:
        parents = [] # type: List[LinkBarButton]
        resource = self.resource # type: Optional[DocResource]
        url = ''
        while resource is not None:
            parents.append(resource.page.createLinkBarButton(url))
            resource = resource.parent
            url += '../'
        yield LinkBarButton(
            label='Home',
            url=url + 'Home',
            icon=styleRoot.addIcon('IconHome')
            )
        yield from reversed(parents)

    def iterChildButtons(self,
                         args: Optional[Arguments]
                         ) -> Iterator[LinkBarButton]:
        for name, page in self.childPages:
            yield page.createLinkBarButton(name + '/')

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(PageProcessor, kwargs['proc'])
        return cast(XMLContent, getattr(proc, 'content'))

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield message
        yield self.presentContent(**kwargs)

class DocErrorResponder(UIResponder[DocPage.Processor]):

    def __init__(self, page: DocPage, proc: DocPage.Processor, error: XML):
        super().__init__(page, proc)
        self.error = error

    def respond(self, response: Response) -> None:
        response.setStatus(500)
        self.proc.error = self.error
        super().respond(response)

class DocResource(Resource):
    """Twisted Resource that serves documentation pages."""

    contentTypes = {
        '.png': 'image/png',
        '.svg': 'image/svg+xml',
        }

    @classmethod
    def registerDocs(cls,
                     packageName: str,
                     parent: Optional['DocResource'] = None
                     ) -> 'DocResource':
        errors = set()

        # Load module.
        try:
            initModule = import_module(packageName) # type: Optional[ModuleType]
        except Exception:
            logging.exception(
                'Error importing documentation module "%s"',
                packageName
                )
            errors.add(DocErrors.MODULE)
            initModule = None

        # Collect metadata.
        metadata = DocMetadata()
        if initModule is not None:
            for name, value in DocMetadata.__dict__.items():
                if name.startswith('_'):
                    continue
                try:
                    value = getattr(initModule, name)
                except AttributeError:
                    logging.exception(
                        'Missing metadata "%s" in module "%s"',
                        name, packageName
                        )
                    errors.add(DocErrors.METADATA)
                else:
                    setattr(metadata, name, value)

        # Create resource.
        resource = cls(packageName, parent)
        page = DocPage(resource, initModule, metadata, errors)
        resource.page = page # pylint: disable=attribute-defined-outside-init

        # Add global processing instruction handlers.
        if initModule is not None:
            piHandlerDict(initModule)['toc'] = page.renderTableOfContents

        # Register children.
        for childName in metadata.children:
            childResource = cls.registerDocs(
                '%s.%s' % (packageName, childName), resource
                )
            resource.putChild(childName.encode(), childResource)

        return resource

    def __init__(self, packageName: str, parent: Optional['DocResource']):
        super().__init__()
        self.packageName = packageName
        self.parent = parent

    def dataFile(self, path: bytes) -> Optional[Resource]:
        """Tries to open a data file at a relative path.
        Returns a static resource on success or None on failure.
        """
        try:
            fileName = path.decode('ascii')
        except UnicodeDecodeError:
            # None of our data files have names with non-ASCII characters.
            return None

        packageName = self.packageName
        if importlib_resources.is_resource(packageName, fileName):
            data = importlib_resources.read_binary(packageName, fileName)
            fileExt = fileName[fileName.index('.'):]
            return Data(data, self.contentTypes[fileExt])
        else:
            return None

    def getChild(self, path: bytes, request: TwistedRequest) -> Resource:
        if path:
            child = self.dataFile(path)
            if child is not None:
                self.putChild(path, child)
                return child
            # Will lead to a 404.
            return super().getChild(path, request)
        else:
            return self

    def render_GET(self, request: TwistedRequest) -> object:
        if not request.path.endswith(b'/'):
            # Redirect to directory, to make sure local assets will be found.
            return redirectTo(request.prepath[-1] + b'/', request)

        return renderAuthenticated(self.page, request)

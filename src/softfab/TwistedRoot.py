# SPDX-License-Identifier: BSD-3-Clause

from functools import partial
from importlib import import_module
from inspect import getmodulename
from types import GeneratorType, ModuleType
from typing import (
    Callable, Dict, Generator, Iterable, Iterator, List, Mapping, Optional,
    Sequence, Type, Union, cast
)
import logging

from markdown import Markdown
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from twisted.cred.error import LoginFailed, Unauthorized
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.error import ConnectionLost
from twisted.python import log
from twisted.python.failure import Failure
from twisted.python.urlpath import URLPath
from twisted.web.http import Request as TwistedRequest
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.web.util import redirectTo
import importlib_resources

from softfab.FabPage import BasePage, LinkBarButton
from softfab.Page import (
    FabResource, InternalError, PageProcessor, Redirect, Redirector, Responder
)
from softfab.SplashPage import SplashPage, startupMessages
from softfab.StyleResources import styleRoot
from softfab.TwistedUtil import PageRedirect
from softfab.UIPage import UIResponder
from softfab.authentication import DisabledAuthPage, NoAuthPage, TokenAuthPage
from softfab.databases import iterDatabasesToPreload
from softfab.pageargs import PageArgs
from softfab.render import (
    InternalErrorPage, NotFoundPage, parseAndProcess, present
)
from softfab.request import Request
from softfab.response import Response
from softfab.schedulelib import ScheduleManager
from softfab.shadowlib import startShadowRunCleanup
from softfab.userlib import UnknownUser, User
from softfab.xmlgen import XML, XMLContent, parseHTML, xhtml

startupLogger = logging.getLogger('ControlCenter.startup')

class ChunkCaller:
    def __init__(self,
            gen: Iterator[Union[Generator, Callable[[], None], None]],
            deferred: Deferred
            ):
        self.__gen = gen
        self.__deferred = deferred
        self.scheduleNext()

    def run(self) -> None:
        try:
            ret = next(self.__gen)
        except StopIteration:
            self.__deferred.callback(None)
            return
        except Exception:
            self.__deferred.errback(Failure())
            return
        else:
            if isinstance(ret, GeneratorType):
                d = Deferred()
                ChunkCaller(ret, d)
                d.addCallback(self.scheduleNext)
            else:
                if callable(ret):
                    try:
                        ret()
                    except Exception:
                        self.__deferred.errback(
                            Failure()
                            )
                        return
                elif ret is not None:
                    self.__deferred.errback(Failure(
                        TypeError('Cannot handle chunk of type %s' % type(ret))
                        ))
                    return
                self.scheduleNext()

    def scheduleNext(self, _: object = None) -> None:
        reactor.callLater(0, self.run)

def callInChunks(gen: Generator) -> Deferred:
    '''Calls a generator until it ends and gives control back to the reactor
    inbetween.
    Can be used to split a long-running operation in chunks without blocking
    the reactor from handling other events.
    A generator can yield:
    - None, this will cause the same generator to be called again
    - another generator, which will be called in chunks, recursively
    - a callable, which will be called as one chunk
    '''
    assert isinstance(gen, GeneratorType)
    d = Deferred()
    ChunkCaller(gen, d)
    return d

class DatabaseLoader:
    recordChunks = 100

    def __init__(self, root: 'SoftFabRoot'):
        self.root = root

    def process(self) -> Iterator[None]:
        for db in iterDatabasesToPreload():
            description = db.description
            failedRecordCount = 0
            startupMessages.addMessage('Loading %s database' % description)
            # Sorting the keys makes it more likely that records that will be
            # used around the same time are close together in memory as well.
            keys = sorted(db.keys())
            yield None # sorting might take a while for big DBs
            recordIndex = 0
            dbLen = len(keys)
            while recordIndex < dbLen:
                recordEnd = min(recordIndex + self.recordChunks, dbLen)
                for key in keys[recordIndex : recordEnd]:
                    try:
                        # We only call this method for its side effect:
                        # caching of the loaded record.
                        db[key]
                    except Exception:
                        # Log a small number of exceptions per DB.
                        # If there are more exceptions, it is likely the
                        # same problem repeated again and again; no point
                        # in flooding the log file.
                        if failedRecordCount < 3:
                            startupLogger.exception(
                                'Failed to load record from %s database',
                                description
                                )
                        failedRecordCount += 1
                recordIndex = recordEnd
                startupMessages.replaceMessage(
                    'Loading %s database, record %d / %d'
                    % (description, recordIndex, dbLen)
                    )
                yield None
            if failedRecordCount != 0:
                startupLogger.error(
                    'Failed to load %d of %d records from %s database',
                    failedRecordCount, dbLen, description
                    )

class PageLoader:

    def __init__(self, root: 'SoftFabRoot'):
        self.root = root

    def __addPage(self, module: ModuleType, pageName: str) -> None:
        pageNamePrefix = pageName + '_'
        pageClasses = tuple(
            cast(Type[FabResource], getattr(module, name))
            for name in dir(module)
            if name.startswith(pageNamePrefix)
            )
        if not pageClasses:
            startupLogger.error(
                'Page module "%s" does not contain any classes named "%s"',
                module.__name__, pageName
                )
            return

        pagesByMethod = {} # type: Dict[str, FabResource]
        name = None
        root = self.root
        for pageClass in pageClasses:
            try:
                page = pageClass()
            except Exception:
                startupLogger.exception(
                    'Error creating instance of page class "%s.%s"',
                    module.__name__, pageClass.__name__
                    )
                continue
            page.debugSupport = root.debugSupport
            if root.anonOperator:
                if not isinstance(page.authenticator, TokenAuthPage):
                    page.authenticator = DisabledAuthPage.instance

            if not issubclass(page.Arguments, PageArgs):
                startupLogger.error(
                    '%s does not inherit from %s.%s',
                    page.Arguments.__qualname__,
                    PageArgs.__module__, PageArgs.__name__
                    )
            if not issubclass(page.Processor, PageProcessor):
                startupLogger.error(
                    '%s does not inherit from %s.%s',
                    page.Processor.__qualname__,
                    PageProcessor.__module__, PageProcessor.__name__
                    )

            className = pageClass.__name__
            index = className.index('_')
            base = className[ : index]
            method = className[index + 1 : ]
            assert method not in pagesByMethod
            pagesByMethod[method] = page
            if base == 'Login':
                setattr(page, 'secureCookie', root.secureCookie)
            if name is None:
                name = base
            else:
                assert name == base
        assert name is not None
        pageResource = PageResource.forMethods(pagesByMethod)
        self.root.putChild(name.encode(), pageResource)

    def process(self) -> None:
        startupMessages.addMessage('Registering pages')
        self.root.putChild(b'docs', DocResource.registerDocs('softfab.docs'))
        pagesPackage = 'softfab.pages'
        for fileName in importlib_resources.contents(pagesPackage):
            moduleName = getmodulename(fileName)
            if moduleName is None or moduleName == '__init__':
                continue
            fullName = pagesPackage + '.' + moduleName
            try:
                module = import_module(fullName)
            except Exception:
                startupLogger.exception(
                    'Error importing page module "%s"', fullName
                    )
            else:
                self.__addPage(module, moduleName)

class PageResource(Resource):
    '''Twisted Resource that serves Control Center pages.
    '''
    isLeaf = True

    @classmethod
    def anyMethod(cls, page: FabResource) -> 'PageResource':
        instance = cls()
        setattr(instance, 'render', partial(renderAuthenticated, page))
        return instance

    @classmethod
    def forMethods(cls,
            pagesByMethod: Mapping[str, FabResource]
            ) -> 'PageResource':
        instance = cls()
        for method, page in pagesByMethod.items():
            setattr(
                instance, 'render_' + method,
                partial(renderAuthenticated, page)
                )
        return instance

markdownConverter = Markdown(
    extensions=[FencedCodeExtension(), TableExtension()]
    )
markdownConverter.stripTopLevelTags = False

class DocMetadata:
    button = 'ERROR'
    children = () # type: Sequence[str]

class DocPage(BasePage['DocPage.Processor', 'DocPage.Arguments']):
    authenticator = NoAuthPage.instance

    class Arguments(PageArgs):
        pass

    class Processor(PageProcessor[Arguments]):
        pass

    def __init__(self,
                 resource: 'DocResource',
                 module: Optional[ModuleType],
                 metadata: DocMetadata,
                 content: Optional[str],
                 errors: Iterable[str]
                 ):
        super().__init__()
        self.resource = resource
        self.module = module
        self.metadata = metadata
        self.content = content
        self.errors = list(errors)
        self.__rendered = None # type: Optional[XML]

    def renderContent(self) -> None:
        if self.__rendered is not None or 'rendering' in self.errors:
            # Already rendered.
            return
        content = self.content
        if content is None:
            # Nothing to render.
            return

        # While Python-Markdown uses ElementTree internally, there is
        # no way to get the full output as a tree, since inline HTML
        # is re-inserted after the tree has been serialized.
        # So unfortunately we have to parse the serialized output.
        markdownConverter.reset()
        xhtmlStr = markdownConverter.convert(content)
        self.__rendered = parseHTML(xhtmlStr)

    def getResponder(self,
                     path: Optional[str],
                     proc: PageProcessor
                     ) -> Responder:
        self.renderContent()
        if self.errors:
            message = xhtml.p(class_='notice')[
                'Error in documentation ', ', '.join(self.errors), '. ',
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

    def pageTitle(self, proc: Processor) -> str:
        if self.content:
            return '(title)'
        else:
            return 'Error'

    def createLinkBarButton(self, url: str) -> LinkBarButton:
        return LinkBarButton(
            label=self.metadata.button,
            url=url,
            icon=styleRoot.addIcon('IconHome'),
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
        resource = self.resource
        for childName in self.metadata.children:
            childResource = resource.children[childName.encode()]
            yield childResource.page.createLinkBarButton(childName + '/')

    def presentContent(self, **kwargs: object) -> XMLContent:
        return self.__rendered

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
        '.html': b'text/html',
        '.css': b'text/css',
        '.png': b'image/png',
        '.svg': b'image/svg+xml',
        }

    @classmethod
    def registerDocs(cls,
                     packageName: str,
                     parent: Optional['DocResource'] = None
                     ) -> 'DocResource':
        # TODO: In Python 3.6, we could use IntFlag instead.
        errors = []

        # Load module.
        initName = packageName + '.__init__'
        try:
            initModule = import_module(initName) # type: Optional[ModuleType]
        except Exception:
            startupLogger.exception(
                'Error importing documentation module "%s"', initName
                )
            errors.append('module')
            initModule = None

        # Load content.
        if initModule is None:
            # If the init module fails to import, resources in the package
            # are inaccessible. Don't try to load them, to avoid error spam.
            content = None
        else:
            contentName = 'contents.md'
            try:
                content = importlib_resources.read_text(
                    packageName, contentName
                    )
            except Exception:
                startupLogger.exception(
                    'Error loading documentation content "%s"', contentName
                    )
                errors.append('content')
                content = None

        # Collect metadata.
        metadata = DocMetadata()
        if initModule is not None:
            for name, value in DocMetadata.__dict__.items():
                if name.startswith('_'):
                    continue
                try:
                    value = getattr(initModule, name)
                except AttributeError:
                    startupLogger.exception(
                        'Missing metadata "%s" in module "%s"', name, initName
                        )
                    errors.append('metadata')
                else:
                    setattr(metadata, name, value)

        # Create resource.
        resource = cls(parent)
        resource.page = DocPage( # pylint: disable=attribute-defined-outside-init
            resource, initModule, metadata, content, errors
            )

        # Register children.
        for childName in metadata.children:
            childResource = cls.registerDocs(
                '%s.%s' % (packageName, childName), resource
                )
            resource.putChild(childName.encode(), childResource)

        return resource

    def __init__(self, parent: Optional['DocResource']):
        super().__init__()
        self.parent = parent

    def getChild(self, path: bytes, request: TwistedRequest) -> Resource:
        if path:
            return super().getChild(path, request)
        else:
            return self

    def render_GET(self, request: TwistedRequest) -> object:
        if not request.path.endswith(b'/'):
            # Redirect to directory, to make sure local assets will be found.
            url = URLPath.fromBytes(request.uri)
            url.path += b'/'
            return redirectTo(str(url).encode('ascii'), request)

        return renderAuthenticated(self.page, request)

def renderAuthenticated(page: FabResource, request: TwistedRequest) -> object:
    def done(result: object) -> None: # pylint: disable=unused-argument
        request.finish()
    def failed(fail: Failure) -> None:
        request.processingFailed(fail)
        # Returning None (implicitly) because the error is handled.
        # Otherwise, it will be logged twice.
    d = renderAsync(page, request)
    d.addCallback(done).addErrback(failed) # pylint: disable=no-member
    return NOT_DONE_YET

class _PlainTextResponder(Responder):

    def __init__(self, status: int, message: str):
        self.__status = status
        self.__message = message

    def respond(self, response: Response) -> None:
        response.setStatus(self.__status, self.__message)
        response.setHeader('Content-Type', 'text/plain')
        response.write(self.__message + '\n')

@inlineCallbacks
def renderAsync(
        page: FabResource, request: TwistedRequest
        ) -> Iterator[Deferred]:
    req = Request(request) # type: Request
    streaming = False
    try:
        authenticator = page.authenticator
        try:
            user = yield authenticator.authenticate(req)
        except LoginFailed as ex:
            responder = authenticator.askForAuthentication(
                req, ex.args[0] if ex.args else None
                )
        except Unauthorized as ex:
            responder = _PlainTextResponder(
                403, ex.args[0] if ex.args else
                        'You are not authorized to perform this operation'
                )
        else:
            responder = yield parseAndProcess(page, req, user) # type: ignore
            streaming = page.streaming
    except Redirect as ex:
        responder = Redirector(ex.url)
    except InternalError as ex:
        logging.error(
            'Internal error processing %s: %s', page.name, str(ex)
            )
        responder = UIResponder(
            InternalErrorPage[PageProcessor](str(ex)),
            PageProcessor(page, req, FabResource.Arguments(), UnknownUser())
            )

    response = Response(request, req.userAgent, streaming)
    try:
        yield present(responder, response)
    except ConnectionLost as ex:
        subPath = req.getSubPath()
        log.msg(
            'Connection lost while presenting page %s%s: %s' % (
                page.name,
                '' if subPath is None else ' item "%s"' % subPath,
                ex
                )
            )

class ResourceNotFound(FabResource[FabResource.Arguments, PageProcessor]):
    authenticator = NoAuthPage.instance

    def checkAccess(self, user: User) -> None:
        pass

    def getResponder(self,
                     path: Optional[str],
                     proc: PageProcessor
                     ) -> Responder:
        notFoundPage = NotFoundPage() # type: NotFoundPage[PageProcessor]
        return UIResponder(notFoundPage, proc)

    def errorResponder(self, ex: Exception, proc: PageProcessor) -> Responder:
        # No processing errors can happen because we use the default processor
        # which does nothing.
        assert False, ex

# Twisted.web paths are bytes.
stylePrefix = styleRoot.urlPrefix.encode()

class SoftFabRoot(Resource):

    def __init__(self,
            debugSupport: bool, anonOperator: bool, secureCookie: bool
            ):
        """Creates a Control Center root resource.

        Parameters:

        debugSupport: bool
            Value for `softfab.FabResource.debugSupport` to set on pages
            registered under this root.

        anonOperator: bool
            Automatically give every client operator privileges to
            pages registered under this root, without forcing a login.

        secureCookie: bool
            Mark the session cookie as secure, meaning it will only
            be submitted over HTTPS.

        """
        self.debugSupport = debugSupport
        self.anonOperator = anonOperator
        self.secureCookie = secureCookie

        Resource.__init__(self)
        self.putChild(b'', PageRedirect('Home'))
        self.putChild(styleRoot.relativeURL.encode(), styleRoot)

        self.defaultResource = PageResource.anyMethod(SplashPage())
        d = callInChunks(self.startup())
        d.addCallback(self.startupComplete)
        d.addErrback(self.startupFailed)

    def startup(self) -> Generator:
        yield DatabaseLoader(self).process()
        yield startShadowRunCleanup
        yield PageLoader(self).process
        # Start schedule processing.
        yield ScheduleManager().trigger

    def startupComplete(self,
            result: None # pylint: disable=unused-argument
            ) -> None:
        # Serve a 404 page for non-existing URLs.
        self.defaultResource = PageResource.anyMethod(ResourceNotFound())

    def startupFailed(self, failure: Failure) -> None:
        startupLogger.error(
            'Error during startup: %s', failure.getTraceback()
            )

        # Try to run the part of the Control Center that did start up
        # properly. This avoids the case where the failure of a rarely used
        # piece of functionality would block the entire SoftFab.
        self.startupComplete(None)

    def getChild(self, path: bytes, request: TwistedRequest) -> Resource:
        # This method is called to dynamically generate a Resource;
        # if a Resource is statically registered this call will not happen.
        if path.startswith(stylePrefix):
            # Also serve style resources under URLs that contain old IDs.
            # This is needed for the Atom feed, where XHTML can be stored by
            # the feed reader for a long time.
            return styleRoot
        else:
            return self.defaultResource

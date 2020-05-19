# SPDX-License-Identifier: BSD-3-Clause

from functools import partial
from mimetypes import guess_type
from types import GeneratorType, ModuleType
from typing import (
    Callable, Dict, Generator, Iterator, Mapping, Optional, Type, Union, cast
)
import logging

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.python.failure import Failure
from twisted.web.http import Request as TwistedRequest
from twisted.web.resource import Resource

from softfab import static
from softfab.Page import FabResource, PageProcessor, Responder
from softfab.SplashPage import SplashPage, startupMessages
from softfab.StyleResources import styleRoot
from softfab.TwistedUtil import PageRedirect
from softfab.UIPage import UIResponder
from softfab.artifacts import createArtifactRoots
from softfab.authentication import DisabledAuthPage, NoAuthPage, TokenAuthPage
from softfab.compat import importlib_resources
from softfab.config import dbDir
from softfab.databases import iterDatabases
from softfab.docserve import DocPage, DocResource
from softfab.pageargs import PageArgs
from softfab.render import NotFoundPage, renderAuthenticated
from softfab.schedulelib import ScheduleManager
from softfab.userlib import User, userDB
from softfab.utils import iterModules
from softfab.webhooks import createWebhooks

startupLogger = logging.getLogger('ControlCenter.startup')

class ChunkCaller:
    def __init__(self,
            gen: Iterator[Union[Generator, Callable[[], None], None]],
            deferred: Deferred
            ):
        super().__init__()
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
                        TypeError(f'Cannot handle chunk '
                                  f'of type {type(ret).__name__}')
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
        super().__init__()
        self.root = root

    def process(self) -> Iterator[None]:
        for db in iterDatabases():
            startupMessages.addMessage(f'Loading {db.description} database')
            # pylint: disable=protected-access
            db._prepareLoad()
            for idx, dummy_ in enumerate(db._iterLoad(startupLogger)):
                if idx % self.recordChunks == 0:
                    yield None
            db._postLoad()

class PageLoader:

    def __init__(self, root: 'SoftFabRoot'):
        super().__init__()
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

        pagesByMethod: Dict[str, FabResource] = {}
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
            if root.anonOperator:
                if not isinstance(page.authenticator, TokenAuthPage):
                    page.authenticator = DisabledAuthPage.instance

            if not issubclass(page.Arguments, PageArgs):
                startupLogger.error(
                    '%s does not inherit from %s.%s',
                    page.Arguments.__qualname__,
                    PageArgs.__module__, PageArgs.__name__
                    )
            processorClass = page.Processor
            if not issubclass(processorClass, PageProcessor):
                startupLogger.error(
                    '%s does not inherit from %s.%s',
                    processorClass.__qualname__,
                    PageProcessor.__module__, PageProcessor.__name__
                    )
            # TODO: Generalize this for all DBs.
            if 'userDB' in processorClass.__annotations__:
                setattr(processorClass, 'userDB', userDB)

            className = pageClass.__name__
            index = className.index('_')
            base = className[ : index]
            method = className[index + 1 : ]
            assert method not in pagesByMethod
            pagesByMethod[method] = page
            if name is None:
                name = base
            else:
                assert name == base
        assert name is not None
        pageResource = PageResource.forMethods(pagesByMethod)
        self.root.putChild(name.encode(), pageResource)

    def process(self) -> None:
        startupMessages.addMessage('Registering pages')
        root = self.root
        root.putChild(b'docs', DocResource.registerDocs('softfab.docs'))
        createArtifactRoots(self.root, dbDir / 'artifacts',
                            self.root.anonOperator)
        root.putChild(b'webhook', createWebhooks(startupLogger))

        # Add files from the 'softfab.static' package.
        for resource in importlib_resources.contents(static):
            if not resource.startswith('_'):
                root.putChild(resource.encode(), StaticResource(resource))

        # Add modules from the 'softfab.pages' package.
        for moduleName, module in iterModules('softfab.pages', startupLogger):
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

class ResourceNotFound(FabResource[FabResource.Arguments, PageProcessor]):
    authenticator = NoAuthPage.instance

    def checkAccess(self, user: User) -> None:
        pass

    def getResponder(self,
                     path: Optional[str],
                     proc: PageProcessor
                     ) -> Responder:
        notFoundPage: NotFoundPage[PageProcessor] = NotFoundPage()
        return UIResponder(notFoundPage, proc)

    def errorResponder(self, ex: Exception, proc: PageProcessor) -> Responder:
        # No processing errors can happen because we use the default processor
        # which does nothing.
        assert False, ex

class StaticResource(Resource):
    """A resource that is included inside the `softfab.static` module.
    """

    def __init__(self, fileName: str):
        super().__init__()
        self.fileName = fileName
        self.contentType, contentEncoding = guess_type(fileName, strict=False)
        # We don't support serving with Content-Encoding yet: we'd have to
        # check the accepted types and possibly decode it before serving.
        # And if there is an encoding reported, the content type will be
        # wrong, so we can't use that either.
        assert contentEncoding is None, contentEncoding

    def render_GET(self, request: TwistedRequest) -> bytes:
        data = importlib_resources.read_binary(static, self.fileName)
        request.setHeader(b'Content-Type', self.contentType)
        request.setHeader(b'Content-Length', str(len(data)).encode())
        return data

class SoftFabRoot(Resource):

    def __init__(self, anonOperator: bool):
        """Creates a Control Center root resource.

        Parameters:

        anonOperator: bool
            Automatically give every client operator privileges to
            pages registered under this root, without forcing a login.

        """
        self.anonOperator = anonOperator

        if anonOperator:
            # TODO: This monkey-patches the class to change all instances
            #       at once, which is fine right now, but would be bad if
            #       we'd want to support multiple roots with different
            #       authentication settings in the future.
            #       However, I expect the authentication approach to be
            #       overhauled before we'll even consider multiple roots.
            DocPage.authenticator = DisabledAuthPage.instance

        super().__init__()
        self.putChild(b'', PageRedirect('Home'))
        self.putChild(styleRoot.relativeURL.encode(), styleRoot)

        self.defaultResource = PageResource.anyMethod(SplashPage())
        d = callInChunks(self.startup())
        d.addCallback(self.startupComplete)
        d.addErrback(self.startupFailed)

    def startup(self) -> Generator:
        yield DatabaseLoader(self).process()
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

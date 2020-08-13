# SPDX-License-Identifier: BSD-3-Clause

from asyncio import sleep
from functools import partial
from mimetypes import guess_type
from types import ModuleType
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Type, cast
import logging

from twisted.web.resource import Resource
from twisted.web.server import Request as TwistedRequest

from softfab import static
from softfab.Page import FabResource, PageProcessor, Responder
from softfab.SplashPage import SplashPage, startupMessages
from softfab.StyleResources import styleRoot
from softfab.TwistedUtil import PageRedirect
from softfab.UIPage import UIResponder
from softfab.artifacts import populateArtifacts
from softfab.authentication import DisabledAuthPage, NoAuthPage, TokenAuthPage
from softfab.compat import importlib_resources
from softfab.config import dbDir
from softfab.configlib import ConfigDB
from softfab.databaselib import Database, SingletonWrapper
from softfab.databases import initDatabases, injectDependencies
from softfab.docserve import DocPage, DocResource
from softfab.joblib import (
    DateRangeMonitor, JobDB, ResultlessJobs, TaskToJobs, UnfinishedJobs
)
from softfab.jobview import JobNotificationObserver
from softfab.newapi import populateAPI
from softfab.pageargs import PageArgs
from softfab.projectlib import Project, ProjectDB, TimezoneUpdater
from softfab.render import NotFoundPage, renderAuthenticated
from softfab.resourcelib import ResourceDB, TaskRunnerTokenProvider
from softfab.resultlib import ResultStorage
from softfab.schedulelib import ScheduleDB, ScheduleManager
from softfab.selectlib import ObservingTagCache
from softfab.tokens import TokenDB
from softfab.userlib import User
from softfab.utils import iterModules
from softfab.webhooks import createWebhooks

startupLogger = logging.getLogger('ControlCenter.startup')

async def preload(databases: Iterable[Database[Any]],
                  recordChunks: int = 100
                  ) -> None:
    for db in databases:
        startupMessages.addMessage(f'Loading {db.description} database')
        # pylint: disable=protected-access
        db._prepareLoad()
        for idx, dummy_ in enumerate(db._iterLoad(startupLogger)):
            if idx % recordChunks == 0:
                await sleep(0)
        db._postLoad()

class PageLoader:

    def __init__(self, root: 'SoftFabRoot', dependencies: Mapping[str, object]):
        super().__init__()
        self.root = root
        self.dependencies = dependencies

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
        dependencies = self.dependencies
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
            injectDependencies(page.authenticator.__class__, dependencies)

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

            injectDependencies(processorClass, dependencies)

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
        populateArtifacts(self.root, dbDir / 'artifacts',
                          self.root.anonOperator, self.dependencies)
        injector = partial(injectDependencies, dependencies=self.dependencies)
        root.putChild(b'webhook', createWebhooks(startupLogger, injector))

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

        # Note: For now, the new-style API is only accessible via
        #       the control socket. When the API is more mature and
        #       supports authentication + authorization, it will
        #       replace the current API.
        self.apiRoot = Resource()

        self.defaultResource = PageResource.anyMethod(SplashPage())

    async def startup(self) -> None:
        try:
            databases = initDatabases(dbDir)

            projectDB = cast(ProjectDB, databases['projectDB'])
            project = cast(Project, SingletonWrapper(projectDB))

            configDB = cast(ConfigDB, databases['configDB'])
            def configTagKeys(project: Project = project) -> Sequence[str]:
                return project.getTagKeys()
            configDB.tagCache = ObservingTagCache(configDB, configTagKeys)

            # Automatically add and remove tokens for Task Runners.
            resourceDB = cast(ResourceDB, databases['resourceDB'])
            tokenDB = cast(TokenDB, databases['tokenDB'])
            resourceDB.addObserver(TaskRunnerTokenProvider(tokenDB))

            await preload(databases.values())

            jobDB = cast(JobDB, databases['jobDB'])
            # TODO: resultStorage was already injected into factories by
            #       initDatabases(), but we have to construct it again
            #       to inject into pages.
            dependencies: Dict[str, object] = dict(
                databases,
                databases=databases.values(),
                project=project,
                resultStorage=ResultStorage(dbDir / 'results'),
                dateRange=DateRangeMonitor(jobDB),
                unfinishedJobs=UnfinishedJobs(jobDB),
                taskToJobs=TaskToJobs(jobDB)
                )

            resultlessJobs = ResultlessJobs(jobDB)
            resultlessJobs.addObserver(JobNotificationObserver(project))

            projectDB.addObserver(TimezoneUpdater())

            populateAPI(self.apiRoot, dependencies)

            injectDependencies(DocPage.Processor, dependencies)
            PageLoader(self, dependencies).process()
            await sleep(0)

            # Start schedule processing.
            scheduleDB = cast(ScheduleDB, databases['scheduleDB'])
            ScheduleManager(configDB, jobDB, scheduleDB).trigger()
        except Exception:
            startupLogger.exception('Error during startup:')
            # Try to run the part of the Control Center that did start up
            # properly. This avoids the case where the failure of a rarely used
            # piece of functionality would block the entire SoftFab.
        finally:
            # Serve a 404 page for non-existing URLs.
            self.defaultResource = PageResource.anyMethod(ResourceNotFound())

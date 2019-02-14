# SPDX-License-Identifier: BSD-3-Clause

from softfab.InternalErrorPage import InternalErrorPage
from softfab.Page import FabResource, InternalError, Redirect, Redirector
from softfab.SplashPage import SplashPage, startupMessages
from softfab.StyleResources import styleRoot
from softfab.TwistedUtil import PageRedirect
from softfab.authentication import NoAuthPage
from softfab.config import homePageName
from softfab.databases import iterDatabasesToPreload
from softfab.render import NotFoundPage, parseAndProcess, present
from softfab.request import Request
from softfab.schedulelib import ScheduleManager
from softfab.userlib import UnknownUser

from twisted.cred.error import LoginFailed
from twisted.internet import defer, reactor
from twisted.internet.error import ConnectionLost
from twisted.python import log
from twisted.python.failure import Failure
from twisted.web import resource, server

from functools import partial
from importlib import import_module
from inspect import getmodulename
from types import GeneratorType
import importlib_resources
import logging

startupLogger = logging.getLogger('ControlCenter.startup')

class ChunkCaller:
    def __init__(self, gen, deferred):
        self.__gen = gen
        self.__deferred = deferred
        self.scheduleNext()

    def run(self):
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
                d = defer.Deferred()
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

    def scheduleNext(self, _ = None):
        reactor.callLater(0, self.run)

def callInChunks(gen):
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
    d = defer.Deferred()
    ChunkCaller(gen, d)
    return d

class DatabaseLoader:
    recordChunks = 100

    def __init__(self, root):
        self.root = root

    def process(self):
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

    def __init__(self, root):
        self.root = root

    def __addPage(self, module, pageName):
        pageClasses = tuple(
            getattr(module, name)
            for name in dir(module)
            if name.partition('_')[0] == pageName
            )
        if not pageClasses:
            startupLogger.error(
                'Page module "%s" does not contain any classes named "%s"',
                module.__name__, pageName
                )
            return

        pagesByMethod = {}
        name = None
        for pageClass in pageClasses:
            className = pageClass.__name__
            index = className.find('_')
            if index == -1:
                base = className
                assert 'GET' not in pagesByMethod
                pagesByMethod['GET'] = pageClass
                assert 'POST' not in pagesByMethod
                pagesByMethod['POST'] = pageClass
            else:
                base = className[ : index]
                method = className[index + 1 : ]
                assert method not in pagesByMethod
                pagesByMethod[method] = pageClass
            if name is None:
                name = base
            else:
                assert name == base
        pageResource = PageResource.forMethods(pagesByMethod)
        self.root.putChild(name.encode(), pageResource)

    def process(self):
        startupMessages.addMessage('Registering pages')
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

class PageResource(resource.Resource):
    '''Twisted Resource that serves Control Center pages.
    '''
    isLeaf = True

    @classmethod
    def anyMethod(cls, pageClass):
        instance = cls()
        setattr(instance, 'render', partial(renderAuthenticated, pageClass()))
        return instance

    @classmethod
    def forMethods(cls, pagesByMethod):
        instance = cls()
        for method, pageClass in pagesByMethod.items():
            setattr(
                instance, 'render_' + method,
                partial(renderAuthenticated, pageClass())
                )
        return instance

def renderAuthenticated(page, request):
    def done(result): # pylint: disable=unused-argument
        request.finish()
    def failed(fail):
        request.processingFailed(fail)
        # Returning None (implicitly) because the error is handled.
        # Otherwise, it will be logged twice.
    d = renderAsync(page, request)
    d.addCallback(done).addErrback(failed) # pylint: disable=no-member
    return server.NOT_DONE_YET

@defer.inlineCallbacks
def renderAsync(page, request):
    try:
        if page.streaming:
            Request(request, UnknownUser()).checkDirect()
        authenticator = page.authenticationWrapper.instance
        try:
            user = yield authenticator.authenticate(request)
        except LoginFailed as ex:
            req = Request(request, UnknownUser())
            responder = proc = authenticator.askForAuthentication(req)
        else:
            req = Request(request, user)
            responder, proc = yield parseAndProcess(page, req)
    except Redirect as ex:
        req = Request(request, UnknownUser())
        responder = proc = Redirector(req, ex.url)
    except InternalError as ex:
        req = Request(request, UnknownUser())
        logging.error(
            'Internal error processing %s: %s', page.name, str(ex)
            )
        responder = proc = InternalErrorPage(req, str(ex))

    try:
        yield present(request, responder, proc)
    except ConnectionLost as ex:
        subPath = req.getSubPath()
        log.msg(
            'Connection lost while presenting page %s%s: %s' % (
                page.name,
                '' if subPath is None else ' item "%s"' % subPath,
                ex
                )
            )

class ResourceNotFound(FabResource):
    authenticationWrapper = NoAuthPage

    def checkAccess(self, req):
        pass

    def getResponder(self, path, proc):
        return NotFoundPage(proc.req)

    def errorResponder(self, ex):
        # No processing errors can happen because we use the default processor
        # which does nothing.
        assert False, ex

# Twisted.web paths are bytes.
stylePrefix = styleRoot.urlPrefix.encode()

class SoftFabRoot(resource.Resource):

    def __init__(self):
        '''Creates a Control Center root resource.
        '''
        resource.Resource.__init__(self)
        self.putChild(b'', PageRedirect(homePageName))
        self.putChild(styleRoot.relativeURL.encode(), styleRoot)

        self.defaultPage = PageResource.anyMethod(SplashPage)
        d = callInChunks(self.startup())
        d.addCallback(self.startupComplete)
        d.addErrback(self.startupFailed)

    def startup(self):
        yield DatabaseLoader(self).process()
        yield PageLoader(self).process
        # Start schedule processing.
        yield ScheduleManager().trigger

    def startupComplete(self, result): # pylint: disable=unused-argument
        # Serve a 404 page for non-existing URLs.
        self.defaultPage = PageResource.anyMethod(ResourceNotFound)

    def startupFailed(self, failure):
        startupLogger.error(
            'Error during startup: %s', failure.getTraceback()
            )

        # Try to run the part of the Control Center that did start up
        # properly. This avoids the case where the failure of a rarely used
        # piece of functionality would block the entire SoftFab.
        self.startupComplete(None)

    def getChild(self, path, request):
        # This method is called to dynamically generate a Resource;
        # if a Resource is statically registered this call will not happen.
        if path.startswith(stylePrefix):
            # Also serve style resources under URLs that contain old IDs.
            # This is needed for the Atom feed, where XHTML can be stored by
            # the feed reader for a long time.
            return styleRoot
        else:
            return self.defaultPage

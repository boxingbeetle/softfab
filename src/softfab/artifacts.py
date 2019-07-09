# SPDX-License-Identifier: BSD-3-Clause

from gzip import GzipFile
from mimetypes import guess_type
from os import fsync, replace
from typing import Dict, IO, Iterable, Iterator, Tuple, Union, cast
from zipfile import BadZipFile, ZipInfo, ZipFile
import logging

from twisted.internet import reactor
from twisted.internet.interfaces import IDelayedCall, IPullProducer
from twisted.internet.threads import deferToThread
from twisted.python.failure import Failure
from twisted.python.filepath import FilePath, InsecurePath
from twisted.web.http import Request as TwistedRequest
from twisted.web.resource import IResource, Resource
from twisted.web.server import NOT_DONE_YET
from twisted.web.util import redirectTo
from zope.interface import implementer

from softfab.joblib import Job, jobDB
from softfab.projectlib import project
from softfab.request import Request
from softfab.resourcelib import runnerFromToken
from softfab.taskrunlib import TaskRun
from softfab.tokens import TokenRole, TokenUser, authenticateToken
from softfab.typing import NoReturn
from softfab.userlib import (
    AccessDenied, AnonGuestUser, SuperUser, UnauthorizedLogin, User,
    checkPrivilege
)


@implementer(IResource)
class ClientErrorResource:
    isLeaf = True
    code = 400

    # PyLint doesn't understand Zope interfaces.
    # pylint: disable=unused-argument

    def __init__(self, message: str):
        self.message = message

    def getChildWithDefault(self,
                            name: bytes,
                            request: TwistedRequest
                            ) -> NoReturn:
        # Will not be called because isLeaf is true.
        assert False

    def putChild(self,
                 path: bytes,
                 child: IResource
                 ) -> NoReturn:
        # Error resources don't support children.
        assert False

    def render(self, request: TwistedRequest) -> bytes:
        request.setResponseCode(self.code)
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
        return self.message.encode() + b'\n'

class UnauthorizedResource(ClientErrorResource):
    code = 401
    realm = 'artifacts'

    def render(self, request: TwistedRequest) -> bytes:
        body = super().render(request)
        request.setHeader(
            b'WWW-Authenticate',
            b'Basic realm="%s"' % self.realm.encode('ascii')
            )
        return body

class AccessDeniedResource(ClientErrorResource):
    code = 403

    @classmethod
    def fromException(cls, ex: AccessDenied) -> 'AccessDeniedResource':
        message = 'Access denied'
        if ex.args:
            message += ': ' + cast(str, ex.args[0])
        return cls(message)

class NotFoundResource(ClientErrorResource):
    code = 404

def _runForRunnerUser(user: User) -> TaskRun:
    """Returns the task run accessible to the given user.
    Raises AccessDenied if the user does not represent a Task Runner
    or the Task Runner is not running any task.
    """

    # Get Task Runner.
    if not isinstance(user, TokenUser):
        raise AccessDenied('This operation is exclusive to Task Runners')
    try:
        runner = runnerFromToken(user)
    except KeyError as ex:
        raise AccessDenied(*ex.args) from ex

    # Get active task from Task Runner.
    run = runner.getRun()
    if run is None:
        raise AccessDenied('Idle Task Runner cannot access jobs')
    else:
        return run

class FactoryResource(Resource):

    def getChild(self, path: bytes, request: TwistedRequest) -> Resource:
        try:
            self.checkAccess()
        except AccessDenied as ex:
            return AccessDeniedResource.fromException(ex)

        try:
            segment = path.decode()
        except UnicodeDecodeError:
            return ClientErrorResource('Path is not valid UTF-8')

        try:
            return self.childForSegment(segment, request)
        except InsecurePath:
            return AccessDeniedResource(
                'Access denied: insecure path segment "%s"' % segment
                )

    def render_GET(self, request: TwistedRequest) -> bytes:
        try:
            self.checkAccess()
        except AccessDenied as ex:
            return AccessDeniedResource.fromException(ex).render(request)

        return self.renderIndex(request)

    def checkAccess(self) -> None:
        raise NotImplementedError

    def childForSegment(self,
                        segment: str,
                        request: TwistedRequest
                        ) -> Resource:
        raise NotImplementedError

    def renderIndex(self, request: TwistedRequest) -> bytes:
        raise NotImplementedError

@implementer(IResource)
class ArtifactAuthWrapper:
    """Wraps a resource tree that requires an authenticated user.

    Inspired by `twisted.web.guard.HTTPAuthSessionWrapper`, but specific
    for our use case which doesn't fit well in Twisted's generic approach.
    """
    isLeaf = False

    def __init__(self, baseDir: FilePath, anonOperator: bool):
        self.baseDir = baseDir
        self.anonOperator = anonOperator

    def _authorizedResource(self, request: TwistedRequest) -> IResource:
        req = Request(request) # type: Request
        user = None

        # There is currently no CC page that supports adding or removing
        # artifacts, so only use logins for read access.
        if req.method in ('GET', 'HEAD'):
            # Use an active login session if available.
            # This also resets the session timeout, so it's worth doing even
            # when anonymous guest access is enabled.
            user = req.loggedInUser()

            if user is None:
                # Perform anonymous read access, if allowed.
                if self.anonOperator:
                    user = SuperUser()
                elif project['anonguest']:
                    user = AnonGuestUser()

        if user is None:
            # Authenticate via token.
            # TODO: There is a lot of overlap with TokenAuthPage.
            try:
                tokenId, password = req.getCredentials()
            except UnicodeDecodeError:
                return AccessDeniedResource('Credentials are not valid UTF-8')

            if tokenId:
                try:
                    token = authenticateToken(tokenId, password)
                except KeyError:
                    return AccessDeniedResource(
                        'Token "%s" does not exist' % tokenId
                        )
                except UnauthorizedLogin as ex:
                    return AccessDeniedResource(
                        'Token authentication failed: %s' % ex.args[0]
                        )
                if token.role is not TokenRole.RESOURCE:
                    return AccessDeniedResource(
                        'Token "%s" is of the wrong type for this operation'
                        % tokenId
                        )
                user = TokenUser(token)

        if user is None:
            return UnauthorizedResource('Please provide an access token')

        return ArtifactRoot(self.baseDir, user)

    def render(self, request: TwistedRequest) -> bytes:
        return self._authorizedResource(request).render(request)

    def getChildWithDefault(self,
                            name: bytes, # pylint: disable=unused-argument
                            request: TwistedRequest
                            ) -> IResource:
        request.postpath.insert(0, request.prepath.pop())
        return self._authorizedResource(request)

class ArtifactRoot(FactoryResource):
    """Top-level job artifact resource."""

    def __init__(self, path: FilePath, user: User):
        super().__init__()
        self.baseDir = path
        self.user = user

    def checkAccess(self) -> None:
        user = self.user
        if user.hasPrivilege('tr/*'):
            return
        else:
            checkPrivilege(
                user, 'j/l',
                'You do not have the necessary permissions to list jobs'
                )

    def childForSegment(self,
                        segment: str,
                        request: TwistedRequest
                        ) -> Resource:
        return JobDayResource(self.baseDir.child(segment), self.user, segment)

    def renderIndex(self, request: TwistedRequest) -> bytes:
        return b'Top-level index not implemented yet'

class JobDayResource(FactoryResource):
    """Resource that represents all jobs created on one day.

    There are file systems that have limits to the number of files
    per directory that can be exceeded by the number of jobs.
    By splitting the job ID it takes a lot longer before such limits
    are reached.
    """

    def __init__(self, path: FilePath, user: User, day: str):
        super().__init__()
        self.baseDir = path
        self.user = user
        self.day = day

    def checkAccess(self) -> None:
        pass

    def childForSegment(self,
                        segment: str,
                        request: TwistedRequest
                        ) -> Resource:
        jobId = '%s-%s' % (self.day, segment)
        try:
            job = jobDB[jobId]
        except KeyError:
            return NotFoundResource('Job "%s" does not exist' % jobId)
        else:
            return JobResource(self.baseDir.child(segment), self.user, job)

    def renderIndex(self, request: TwistedRequest) -> bytes:
        return b'Job day index not implemented yet'

class JobResource(FactoryResource):
    """Resource that represents one job."""

    def __init__(self, path: FilePath, user: User, job: Job):
        super().__init__()
        self.baseDir = path
        self.user = user
        self.job = job

    def checkAccess(self) -> None:
        user = self.user
        if user.hasPrivilege('tr/*'):
            job = _runForRunnerUser(user).getJob()
            if self.job.getId() != job.getId():
                raise AccessDenied('Task Runner is running a different job')
        else:
            # TODO: Our privilege system is too fine grained.
            checkPrivilege(
                user, 'j/a',
                'You do not have the necessary permissions to access jobs'
                )
            checkPrivilege(
                user, 't/l',
                'You do not have the necessary permissions to list tasks'
                )

    def childForSegment(self,
                        segment: str,
                        request: TwistedRequest
                        ) -> Resource:
        task = self.job.getTask(segment)
        if task is None:
            return NotFoundResource(
                'Task "%s" does not exist in this job' % segment
                )
        return TaskResource(
            self.baseDir.child(segment),
            self.user,
            task.getLatestRun()
            )

    def renderIndex(self, request: TwistedRequest) -> bytes:
        return b'Job index not implemented yet'

class TaskResource(FactoryResource):
    """Resource that represents one task run."""

    def __init__(self, path: FilePath, user: User, run: TaskRun):
        super().__init__()
        self.baseDir = path
        self.user = user
        self.run = run

    def checkAccess(self) -> None:
        user = self.user
        if user.hasPrivilege('tr/*'):
            run = _runForRunnerUser(user)
            if self.run.getId() != run.getId():
                raise AccessDenied('Task Runner is running a different task')
        else:
            checkPrivilege(
                user, 't/a',
                'You do not have the necessary permissions to access tasks'
                )

    def childForSegment(self,
                        segment: str,
                        request: TwistedRequest
                        ) -> Resource:
        for ext, contentClass, plainClass in (
                ('.gz', GzippedArtifact, PlainGzipArtifact),
                ('.zip', ZippedArtifact, PlainZipArtifact)
                ):
            # Serve the archive's contents.
            path = self.baseDir.child(segment + ext)
            if path.isfile():
                return contentClass(path)
            # Serve the archive itself.
            if segment.endswith(ext):
                path = self.baseDir.child(segment)
                if request.method == b'PUT' or path.isfile():
                    return plainClass(path)

        if request.method == b'PUT':
            return ClientErrorResource('Uploads must use gzip or ZIP format')
        else:
            return NotFoundResource(
                'No artifact named "%s" exists for this task' % segment
                )

    def renderIndex(self, request: TwistedRequest) -> bytes:
        return b'Listing task subresources is not implemented yet'

@implementer(IPullProducer)
class FileProducer:
    blockSize = 16384

    @classmethod
    def serve(cls, inp: IO[bytes], request: TwistedRequest) -> 'FileProducer':
        producer = cls(inp, request)
        request.registerProducer(producer, False)
        return producer

    def __init__(self, inp: IO[bytes], request: TwistedRequest):
        self.inp = inp
        self.request = request

    def resumeProducing(self) -> None:
        # Read one block of data.
        inp = self.inp
        try:
            data = inp.read(self.blockSize)
        except OSError as ex:
            logging.error('Read error serving artifact "%s": %s', inp.name, ex)
            # We don't have any way to communicate the error to the user
            # agent, so treat read errors like end-of-file.
            data = bytes()

        request = self.request
        if data:
            request.write(data)
        else:
            # End of file.
            try:
                inp.close()
            except OSError:
                pass
            request.unregisterProducer()
            request.finish()

    def stopProducing(self) -> None:
        pass

class PlainArtifact(Resource):
    """Base class for accessing an artifact's archive file directly."""

    contentType = b'application/octet-stream'

    putBlockSize = 65536
    """Process files from PUT in chunks of this many bytes.
    Since PUT is handled on a separate thread, the limit is there only
    to avoid hogging memory, not the CPU.
    """

    def __init__(self, path: FilePath):
        super().__init__()
        self.path = path

    def getChild(self, path: bytes, request: TwistedRequest) -> Resource:
        return NotFoundResource('Cannot access subitems from full archive')

    def render_GET(self, request: TwistedRequest) -> object:
        request.setHeader(b'Content-Type', self.contentType)
        FileProducer.serve(self.path.open(), request)
        return NOT_DONE_YET

    def render_PUT(self, request: TwistedRequest) -> object:
        path = self.path

        if path.isfile():
            request.setResponseCode(409)
            request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
            return b'Artifacts cannot be overwritten\n'

        # Note: Twisted buffers the entire upload into 'request.content'
        #       prior to calling our render method.
        #       There doesn't seem to be a clean way to handle streaming
        #       uploads in Twisted; we'd have to set site.requestFactory
        #       to a request implementation that overrides gotLength() or
        #       handleContentChunk(), both of which are documented as
        #       "not intended for users".

        # Do the actual store in a separate thread, so we don't have to worry
        # about slow operations hogging the reactor thread.
        deferToThread(self._storeArtifact, request.content, path) \
            .addCallback(self.putDone, request) \
            .addErrback(self.putFailed, request)
        return NOT_DONE_YET

    @classmethod
    def putDone(cls,
                result: None, # pylint: disable=unused-argument
                request: TwistedRequest
                ) -> None:
        request.setResponseCode(201)
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
        request.write(b'Artifact stored\n')
        request.finish()

    @classmethod
    def putFailed(cls, fail: Failure, request: TwistedRequest) -> None:
        ex = fail.value
        if isinstance(ex, ValueError):
            request.setResponseCode(415)
            request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
            request.write(('%s\n' % ex).encode())
            request.finish()
        else:
            request.processingFailed(fail)
        # Returning None (implicitly) because the error is handled.
        # Otherwise, it will be logged twice.

    @classmethod
    def _storeArtifact(cls, content: IO[bytes], path: FilePath) -> None:
        """Verify and store an artifact from a temporary file.
        If the file is valid, store it at the given path.
        If the file is not valid, raise ValueError.
        """

        cls.verify(content)

        # Copy content.
        content.seek(0, 0)
        uploadPath = path.siblingExtension('.part')
        path.parent().makedirs(ignoreExistingDirectory=True)
        with uploadPath.open('wb') as out:
            while True:
                data = content.read(cls.putBlockSize)
                if not data:
                    break
                out.write(data)
            out.flush()
            fsync(out.fileno())
        replace(uploadPath.path, path.path)
        path.changed()

    @classmethod
    def verify(cls, archive: IO[bytes]) -> None:
        """Verify the integrity of the archive file.
        Return nothing if the file is valid, raise ValueError otherwise.
        """
        raise NotImplementedError

class PlainGzipArtifact(PlainArtifact):
    """Single-file artifact stored as a gzip file."""

    contentType = b'application/gzip'

    @classmethod
    def verify(cls, archive: IO[bytes]) -> None:
        try:
            with GzipFile(fileobj=archive) as gz:
                while True:
                    data = gz.read(cls.putBlockSize)
                    if not data:
                        break
        except (OSError, EOFError) as ex:
            raise ValueError(
                'Uploaded data is not a valid gzip file: %s' % ex
                ) from ex

class GzippedArtifact(Resource):
    """Single-file artifact stored as gzip file."""

    def __init__(self, path: FilePath):
        super().__init__()
        self.path = path

    def getChild(self, path: bytes, request: TwistedRequest) -> Resource:
        return NotFoundResource(
            'Artifact "%s" cannot not contain subitems'
            % request.prepath[-2].decode()
            )

    def render_GET(self, request: TwistedRequest) -> object:
        path = self.path

        contentType, contentEncoding = guess_type(path.basename(), strict=False)
        if contentType is None:
            contentType = 'application/octet-stream'
        request.setHeader(b'Content-Type', contentType.encode())
        if contentEncoding is not None:
            # TODO: Check for gzip in the Accept-Encoding header.
            #       In practice though, gzip is accepted universally.
            request.setHeader(b'Content-Encoding', contentEncoding.encode())

        FileProducer.serve(path.open(), request)
        return NOT_DONE_YET

class PlainZipArtifact(PlainArtifact):
    """Single-file artifact stored as a ZIP file."""

    contentType = b'application/zip'

    @classmethod
    def verify(cls, archive: IO[bytes]) -> None:
        try:
            with ZipFile(archive) as zipFile:
                badFileName = zipFile.testzip()
                if badFileName is not None:
                    raise ValueError(
                        'ZIP file entry "%s" is corrupted' % badFileName
                        )
                # Raise ValueError on name clashes.
                ZipTreeNode.build(zipFile)
        except BadZipFile as ex:
            raise ValueError(
                'Uploaded data is not a valid ZIP file: %s' % ex
                ) from ex

class ZippedArtifact(Resource):
    """Directory of artifacts stored as ZIP file."""

    isLeaf = True

    def __init__(self, zipPath: FilePath):
        super().__init__()
        self.zipPath = zipPath

    def render_GET(self, request: TwistedRequest) -> object:
        # Convert path to Unicode.
        try:
            segments = [segment.decode() for segment in request.postpath]
        except UnicodeDecodeError:
            return ClientErrorResource('Path is not valid UTF-8')

        # Look up path in ZIP directory tree.
        tree = ZipTree.get(self.zipPath.path)
        try:
            node = tree.find(segments)
        except KeyError:
            return NotFoundResource(
                'No ZIP entry matches path "%s"' % '/'.join(segments)
                )

        if isinstance(node, ZipTreeNode):
            # Path ends at a directory.
            if not request.path.endswith(b'/'):
                path = (request.postpath or request.prepath)[-1]
                return redirectTo(path + b'/', request)
            request.setResponseCode(500)
            request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
            return b'ZIP directory listing not yet implemented\n'
        else:
            # Path ends at a file.
            return self.renderFile(request, tree.zipFile, node)

    def renderFile(self,
                   request: TwistedRequest,
                   zipFile: ZipFile,
                   info: ZipInfo
                   ) -> object:
        """Serve a file entry from a ZIP file.
        """

        # Determine content type.
        contentType, encoding = guess_type(info.filename, strict=False)
        if encoding is not None:
            # We want contents to be served as-is, not automatically
            # decoded by the browser.
            contentType = 'application/' + encoding
        if contentType is None:
            contentType = 'application/octet-stream'
        request.setHeader(b'Content-Type', contentType.encode())

        # Decompress and send to user agent.
        FileProducer.serve(zipFile.open(info), request)
        return NOT_DONE_YET

class ZipTreeNode:

    @classmethod
    def build(cls, zipFile: ZipFile) -> 'ZipTreeNode':
        root = cls()
        for info in zipFile.infolist():
            segments = iter(info.filename.split('/'))
            root.add(next(segments), segments, info)
        return root

    def __init__(self) -> None:
        self.children = {} # type: Dict[str, Union[ZipTreeNode, ZipInfo]]

    def add(self, name: str, remainder: Iterator[str], info: ZipInfo) -> None:
        children = self.children
        child = children.get(name)
        try:
            nextName = next(remainder)
        except StopIteration:
            if name:
                if child is None:
                    # File entry.
                    children[name] = info
                elif isinstance(child, ZipInfo):
                    raise ValueError('Duplicate file: "%s"' % info.filename)
                else:
                    raise ValueError(
                        'File overlaps with directory: "%s"' % info.filename
                        )
            else:
                # Directory entry.
                pass
        else:
            if child is None:
                children[name] = child = ZipTreeNode()
            elif isinstance(child, ZipInfo):
                raise ValueError(
                    'File overlaps with directory: "%s"' % child.filename
                    )
            child.add(nextName, remainder, info)

class ZipTree:
    cache = {} # type: Dict[str, Tuple[ZipTree, IDelayedCall]]
    timeout = 30

    @classmethod
    def get(cls, zipPath: str) -> 'ZipTree':
        cache = cls.cache
        try:
            tree, closeCall = cache[zipPath]
        except KeyError:
            # Note: When reading a very large file or serving it to a very
            #       slow client, the cache timeout could happen while a read
            #       stream is still open. It is important that we construct
            #       the ZipFile from a path rather than a file-like object,
            #       since the former makes it use a refcount and not close
            #       the underlying file until the read stream is done with it.
            zipFile = ZipFile(zipPath)
            tree = cls(zipFile)
            closeCall = reactor.callLater(cls.timeout, cls.close, zipFile)
            cache[zipPath] = tree, closeCall
        else:
            closeCall.reset(cls.timeout)
        return tree

    @classmethod
    def close(cls, zipFile: ZipFile) -> None:
        path = zipFile.filename
        assert path is not None
        del cls.cache[path]
        try:
            zipFile.close()
        except OSError as ex:
            logging.warning('Error closing ZIP file "%s": %s', path, ex)

    def __init__(self, zipFile: ZipFile):
        self.zipFile = zipFile
        self.root = ZipTreeNode.build(zipFile)

    def find(self, segments: Iterable[str]) -> Union[ZipInfo, ZipTreeNode]:
        """Look up a file path in this ZIP directory tree.
        Return a ZipInfo if a file is found.
        Return a ZipTreeNode if a directory is found.
        Raise KeyError if no match is found.
        """
        node = self.root # type: Union[ZipInfo, ZipTreeNode]
        for segment in segments:
            if isinstance(node, ZipTreeNode):
                if segment:
                    node = node.children[segment]
            else:
                raise KeyError(segment)
        return node

def createArtifactRoot(baseDir: str, anonOperator: bool) -> IResource:
    path = FilePath(baseDir)
    return ArtifactAuthWrapper(path, anonOperator)

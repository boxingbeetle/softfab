# SPDX-License-Identifier: BSD-3-Clause

from functools import partial
from gzip import GzipFile, open as openGzip
from mimetypes import guess_type
from os import fsync, replace
from pathlib import Path
# https://github.com/PyCQA/pylint/issues/3499
from struct import Struct  # pylint: disable=no-name-in-module
from typing import (
    IO, Any, Dict, Iterable, Iterator, Mapping, Optional, Tuple, Union
)
from urllib.parse import unquote_plus
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo
import logging

from passlib.pwd import genword
from twisted.internet import reactor
from twisted.internet.interfaces import IDelayedCall, IPullProducer
from twisted.internet.threads import deferToThread
from twisted.python.failure import Failure
from twisted.python.filepath import FilePath, InsecurePath
from twisted.web.http import Request as TwistedRequest
from twisted.web.resource import IResource, Resource
from twisted.web.server import NOT_DONE_YET
from twisted.web.util import Redirect, redirectTo
from zope.interface import implementer
import attr

from softfab.StyleResources import styleRoot
from softfab.TwistedUtil import (
    AccessDeniedResource, ClientErrorResource, NotFoundResource,
    UnauthorizedResource
)
from softfab.UIPage import fixedHeadItems
from softfab.joblib import Job, jobDB
from softfab.projectlib import project
from softfab.reportview import ReportPresenter, createPresenter
from softfab.request import Request
from softfab.resourcelib import resourceDB
from softfab.taskrunlib import TaskRun
from softfab.tokens import TokenDB, TokenRole, TokenUser, authenticateToken
from softfab.useragent import AcceptedEncodings
from softfab.userlib import (
    AccessDenied, AnonGuestUser, SuperUser, UnauthorizedLogin, User,
    checkPrivilege
)
from softfab.xmlgen import xhtml

SANDBOX_RULES = ' '.join('allow-' + perm for perm in (
    'forms', 'modals', 'popups', 'scripts'
    ))
"""Browser permissions granted to sandboxed documents.

This probably needs to be tweaked over time; please submit an issue
if you find this too restrictive or not restrictive enough.
"""

@attr.s(auto_attribs=True, frozen=True)
class SandboxedPath:
    """A file path within an artifact sandbox."""

    sandbox: 'ArtifactSandbox'
    filePath: FilePath
    path: Tuple[str, ...]

    def child(self, name: str) -> 'SandboxedPath':
        """Return a sandboxed path that is a child of this path."""
        return SandboxedPath(self.sandbox,
                             self.filePath.child(name),
                             self.path + (name,))

    def createURL(self) -> str:
        """Return a relative URL with a random key under which
        this sandboxed path is temporarily available.
        """
        key = self.sandbox.keyFor(self)
        return '/'.join(('sandbox', key) + self.path)

@attr.s(auto_attribs=True)
@implementer(IResource)
class ArtifactSandbox:
    """Serves the actual artifacts in a sandbox.
    """
    isLeaf = False

    keyTimeout = 30
    keyLength = 6

    baseDir: FilePath
    _activeKeys: Dict[str, SandboxedPath] = \
        attr.ib(repr=False, init=False, factory=dict)

    @property
    def rootPath(self) -> SandboxedPath:
        return SandboxedPath(self, self.baseDir, ())

    def keyFor(self, path: SandboxedPath) -> str:
        """Return a key for accessing the given sandbox path.
        """

        # Skip key generation if artifacts are public.
        if project.anonguest:
            return 'anon'

        key = genword(length=self.keyLength)
        self._activeKeys[key] = path
        reactor.callLater(self.keyTimeout, self.keyExpired, key)
        return key

    def keyExpired(self, key: str) -> None:
        del self._activeKeys[key]

    def render(self, request: TwistedRequest) -> bytes:
        return AccessDeniedResource('Missing key').render(request)

    def getChildWithDefault(self,
                            name: bytes,
                            request: TwistedRequest
                            ) -> IResource:
        # Prevent leaking sandbox key to external sites.
        request.setHeader(b'Referrer-Policy', b'origin-when-cross-origin')
        # Repeat sandbox rules, in case artifact is viewed outside iframe.
        request.setHeader(b'Content-Security-Policy',
                          b'sandbox %s;' % SANDBOX_RULES.encode())

        origin = request.getHeader(b'Origin')

        # Handle anonymous guest access.
        if name == b'anon' and project.anonguest:
            if origin is not None:
                request.setHeader(b'Access-Control-Allow-Origin', b'*')
            return SandboxedResource(self.baseDir, ())

        # Verify that request came from null origin.
        if origin is not None:
            if origin == b'null':
                request.setHeader(b'Access-Control-Allow-Origin', b'null')
            else:
                return AccessDeniedResource(
                    'Sandboxed content requested from non-null origin'
                    )

        try:
            key = name.decode('ascii')
        except UnicodeDecodeError:
            return ClientErrorResource('Key contains invalid characters')

        try:
            path = self._activeKeys[key]
        except KeyError:
            # Key does not exist or is no longer valid.
            # Redirect to non-sandboxed path to acquire new key.
            return Redirect(b'/'.join(
                [b'..'] * (len(request.postpath) + 1) + request.postpath
                ))
        else:
            return SandboxedResource(self.baseDir, path.path)

@attr.s(auto_attribs=True)
@implementer(IResource)
class SandboxedResource:
    """An intermediate directory in a sandboxed path."""

    isLeaf = False

    dirPath: FilePath
    rightPath: Tuple[str, ...]

    def render(self, request: TwistedRequest) -> bytes:
        return AccessDeniedResource('Incomplete path').render(request)

    def getChildWithDefault(
            self,
            name: bytes,
            request: TwistedRequest
            ) -> IResource:
        try:
            nameStr = name.decode()
        except UnicodeDecodeError:
            return ClientErrorResource('Path is not valid UTF-8')

        # Take one step along the prescribed path.
        rightPath = self.rightPath
        if rightPath:
            if rightPath[0] != nameStr:
                return AccessDeniedResource('You have strayed from the path')
            rightPath = rightPath[1:]

        dirPath = self.dirPath
        subDirPath = dirPath.child(nameStr)
        if subDirPath.isdir():
            return SandboxedResource(subDirPath, rightPath)
        for ext, contentClass in (('.gz', GzippedArtifact),
                                  ('.zip', ZippedArtifact)):
            filePath = dirPath.child(nameStr + ext)
            if filePath.isfile():
                return contentClass(filePath)

        # Redirect to non-sandboxed URL.
        # It is possible the user edited the URL to request a different
        # artifact or different presentation of the artifact that doesn't
        # exist in the sandbox.
        return Redirect(b'/'.join(
            [b'..'] * (len(request.prepath) - 1) + request.prepath[2:]
            ))

def _runForRunnerUser(user: User) -> TaskRun:
    """Returns the task run accessible to the given user.
    Raises AccessDenied if the user does not represent a Task Runner
    or the Task Runner is not running any task.
    """

    # Get Task Runner.
    if not isinstance(user, TokenUser):
        raise AccessDenied('This operation is exclusive to Task Runners')
    try:
        runner = resourceDB.runnerFromToken(user)
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
            segment = unquote_plus(path.decode(), errors='strict')
        except UnicodeError:
            return ClientErrorResource('Path is not valid')

        if not segment:
            # Empty segment in the middle of a path is probably a typo,
            # while empty segment at the end should render index.
            return self

        try:
            return self.childForSegment(segment, request)
        except InsecurePath:
            return AccessDeniedResource(
                f'Access denied: insecure path segment "{segment}"'
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

    def __init__(self,
                 path: SandboxedPath,
                 anonOperator: bool,
                 tokenDB: TokenDB
                 ):
        super().__init__()
        self.path = path
        self.anonOperator = anonOperator
        self.tokenDB = tokenDB

    def _authorizedResource(self, request: TwistedRequest) -> IResource:
        req: Request = Request(request)
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
                elif project.anonguest:
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
                    token = authenticateToken(self.tokenDB, tokenId, password)
                except KeyError:
                    return AccessDeniedResource(
                        f'Token "{tokenId}" does not exist'
                        )
                except UnauthorizedLogin as ex:
                    return AccessDeniedResource(
                        f'Token authentication failed: {ex.args[0]}'
                        )
                if token.role is not TokenRole.RESOURCE:
                    return AccessDeniedResource(
                        f'Token "{tokenId}" is of the wrong type '
                        f'for this operation'
                        )
                user = TokenUser(token)

        if user is None:
            return UnauthorizedResource('artifacts',
                                        'Please provide an access token')

        return ArtifactRoot(self.path, user)

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

    def __init__(self, path: SandboxedPath, user: User):
        super().__init__()
        self.path = path
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
        return JobDayResource(self.path.child(segment), self.user, segment)

    def renderIndex(self, request: TwistedRequest) -> bytes:
        return b'Top-level index not implemented yet'

class JobDayResource(FactoryResource):
    """Resource that represents all jobs created on one day.

    There are file systems that have limits to the number of files
    per directory that can be exceeded by the number of jobs.
    By splitting the job ID it takes a lot longer before such limits
    are reached.
    """

    def __init__(self, path: SandboxedPath, user: User, day: str):
        super().__init__()
        self.path = path
        self.user = user
        self.day = day

    def checkAccess(self) -> None:
        pass

    def childForSegment(self,
                        segment: str,
                        request: TwistedRequest
                        ) -> Resource:
        jobId = f'{self.day}-{segment}'
        try:
            job = jobDB[jobId]
        except KeyError:
            return NotFoundResource(f'Job "{jobId}" does not exist')
        else:
            return JobResource(self.path.child(segment), self.user, job)

    def renderIndex(self, request: TwistedRequest) -> bytes:
        return b'Job day index not implemented yet'

class JobResource(FactoryResource):
    """Resource that represents one job."""

    def __init__(self, path: SandboxedPath, user: User, job: Job):
        super().__init__()
        self.path = path
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
                f'Task "{segment}" does not exist in this job'
                )
        run = task.getLatestRun()
        return TaskResource(self.path.child(segment), self.user, run)

    def renderIndex(self, request: TwistedRequest) -> bytes:
        return b'Job index not implemented yet'

class TaskResource(FactoryResource):
    """Resource that represents one task run."""

    def __init__(self, path: SandboxedPath, user: User, run: TaskRun):
        super().__init__()
        self.path = path
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
        path = self.path.child(segment)
        dirPath = self.path.filePath
        for ext, plainClass in (('.gz', PlainGzipArtifact),
                                ('.zip', PlainZipArtifact)):
            # Serve the archive's contents.
            filePath = dirPath.child(segment + ext)
            if filePath.isfile():
                return self.reportForFile(filePath, path, request)
            # Serve the archive itself.
            if segment.endswith(ext):
                filePath = path.filePath
                if request.method == b'PUT' or filePath.isfile():
                    return plainClass(filePath)

        if request.method == b'PUT':
            return ClientErrorResource('Uploads must use gzip or ZIP format')
        else:
            return NotFoundResource(
                f'No artifact named "{segment}" exists for this task'
                )

    def reportForFile(self,
                      filePath: FilePath,
                      sandboxedPath: SandboxedPath,
                      request: TwistedRequest
                      ) -> Resource:

        if filePath.splitext()[1] == '.gz':
            # Try to use fancy formatting.
            fileName = sandboxedPath.path[-1]
            presenter = createPresenter(
                            partial(openGzip, filePath.path), fileName)
            if presenter is not None:
                # pylint: disable=too-many-function-args
                # https://github.com/PyCQA/pylint/issues/3492
                return ReportResource(presenter, fileName)

        # Redirect to sandbox to serve the report as-is.
        urlPath = [b'..'] * (len(request.postpath) - 1 +
                             len(sandboxedPath.path))
        urlPath.append(sandboxedPath.createURL().encode())
        urlPath += request.postpath
        return Redirect(b'/'.join(urlPath))

    def renderIndex(self, request: TwistedRequest) -> bytes:
        return b'Listing task subresources is not implemented yet'

@attr.s(auto_attribs=True)
class ReportResource(Resource):
    """Presents a report as an HTML document."""
    isLeaf = True

    presenter: ReportPresenter
    fileName: str

    def render_GET(self, request: TwistedRequest) -> object:
        presenter = self.presenter
        depth = len(request.prepath) - 1
        styleURL = '../' * depth + styleRoot.relativeURL
        request.write(b'<!DOCTYPE html>\n')
        request.write(
            xhtml.html[
                xhtml.head[
                    fixedHeadItems,
                    presenter.headItems(),
                    xhtml.title[f'Report: {self.fileName}']
                    ].present(styleURL=styleURL),
                xhtml.body[
                    xhtml.div(class_='body')[
                        presenter.presentBody()
                        ]
                    ]
                ].flattenXML().encode()
            )
        request.finish()
        return NOT_DONE_YET

@implementer(IPullProducer)
class FileProducer:
    blockSize = 16384

    _variableHeaderLengths = Struct('<2H')
    _gzipFooter = Struct('<2I')

    @classmethod
    def servePlain(cls,
                   inp: IO[bytes],
                   request: TwistedRequest
                   ) -> 'FileProducer':
        """Serves an input stream as-is."""
        return cls._serve(cls.ioBlockGen(inp), request)

    @classmethod
    def serveZipEntry(cls,
                      inp: IO[bytes],
                      info: ZipInfo,
                      request: TwistedRequest
                      ) -> 'FileProducer':
        """Serves a deflate-compressed ZIP file entry as a gzip file."""

        request.setHeader(b'Content-Encoding', b'gzip')

        # Seek to start of deflate stream.
        offset = info.header_offset
        inp.seek(offset + 26)
        nameLen, extraLen = cls._variableHeaderLengths.unpack(inp.read(4))
        inp.seek(offset + 30 + nameLen + extraLen)

        size = info.compress_size
        footer = cls._gzipFooter.pack(info.CRC, info.file_size)
        return cls._serve(cls.gzipBlockGen(inp, size, footer), request)

    @classmethod
    def _serve(cls,
               blockGen: Iterator[bytes],
               request: TwistedRequest
               ) -> 'FileProducer':
        producer = cls(blockGen, request)
        request.registerProducer(producer, False)
        return producer

    @classmethod
    def ioBlockGen(cls,
                   inp: IO[bytes],
                   size: Optional[int] = None
                   ) -> Iterator[bytes]:
        numBytes = cls.blockSize
        while True:
            if size is not None:
                numBytes = min(numBytes, size)
            try:
                data = inp.read(numBytes)
            except OSError as ex:
                logging.error('Read error serving artifact "%s": %s',
                              inp.name, ex)
                # We don't have any way to communicate the error to the user
                # agent, so treat read errors like end-of-file.
                break
            else:
                if data:
                    yield data
                    if size is not None:
                        size -= len(data)
                        if size == 0:
                            break
                else:
                    break
        try:
            inp.close()
        except OSError as ex:
            logging.error('Close error serving artifact "%s": %s',
                          inp.name, ex)

    @classmethod
    def gzipBlockGen(cls,
                     inp: IO[bytes],
                     size: int,
                     footer: bytes
                     ) -> Iterator[bytes]:
        yield b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03'
        yield from cls.ioBlockGen(inp, size)
        yield footer

    def __init__(self, blockGen: Iterator[bytes], request: TwistedRequest):
        super().__init__()
        self.blockGen = blockGen
        self.request = request

    def resumeProducing(self) -> None:
        request = self.request
        try:
            data = next(self.blockGen)
        except StopIteration:
            request.unregisterProducer()
            request.finish()
        else:
            request.write(data)

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
        request.setHeader(b'Content-Disposition', b'attachment')
        FileProducer.servePlain(self.path.open(), request)
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
            request.write((f'{ex}\n').encode())
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
                f'Uploaded data is not a valid gzip file: {ex}'
                ) from ex

class GzippedArtifact(Resource):
    """Single-file artifact stored as a gzip file."""

    def __init__(self, path: FilePath):
        super().__init__()
        self.path = path

    def getChild(self, path: bytes, request: TwistedRequest) -> Resource:
        name = request.prepath[-2].decode()
        return NotFoundResource(f'Artifact "{name}" cannot contain subitems')

    def render_GET(self, request: TwistedRequest) -> object:
        path = self.path

        contentType, contentEncoding = guess_type(path.basename(), strict=False)
        if contentType is None:
            contentType = 'application/octet-stream'
        elif contentType.startswith('text/'):
            # Encoding autodetection in browsers is pretty poor, so we're
            # likely better off forcing UTF-8. Most gzipped text files are
            # logs and we tell the wrappers to output in UTF-8.
            # TODO: Perform an encoding detection on upload, or just preserve
            #       the Content-Type header of the PUT request, if present.
            # TODO: Convert to UTF-8 if the user agent requests it using
            #       the Accept-Charset header. MDN says modern browsers omit
            #       this header, but a non-browser client could set it to
            #       indicate it is only willing to deal with UTF-8.
            #       If no particular encoding is requested, just serve the
            #       file as it was uploaded.
            contentType += '; charset=UTF-8'
        request.setHeader(b'Content-Type', contentType.encode())
        request.setHeader(b'Content-Disposition', b'inline')

        # Serve data in compressed form if user agent accepts it.
        if contentEncoding is None:
            decompress = False
        else:
            accept = AcceptedEncodings.parse(
                                        request.getHeader('accept-encoding'))
            decompress = 4.0 * accept[contentEncoding] < accept['identity']
            if not decompress:
                request.setHeader('Content-Encoding', contentEncoding)
        if decompress:
            # Note: Passing 'fileobj' to GzipFile appears more elegant,
            #       but that stream isn't closed when GzipFile is closed.
            stream = openGzip(path.path)
        else:
            stream = path.open()

        FileProducer.servePlain(stream, request)
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
                        f'ZIP file entry "{badFileName}" is corrupted'
                        )
                # Raise ValueError on name clashes.
                ZipTreeNode.build(zipFile)
        except BadZipFile as ex:
            raise ValueError(
                f'Uploaded data is not a valid ZIP file: {ex}'
                ) from ex

class ZippedArtifact(Resource):
    """Directory of artifacts stored as ZIP file."""

    isLeaf = True

    def __init__(self, zipPath: FilePath):
        super().__init__()
        self.zipPath = zipPath

    def render_OPTIONS(self, request: TwistedRequest) -> bytes:
        # Generic HTTP options.
        request.setHeader(b'Allow', b'GET, HEAD, OPTIONS')

        # CORS options.
        origin = request.getHeader(b'Origin')
        if origin is not None:
            # Grant all requested headers.
            requestedHeaders = request.getHeader(
                    b'Access-Control-Request-Headers') or b''
            request.setHeader(b'Access-Control-Allow-Headers',
                              requestedHeaders)

            # The information returned does not expire, but the sanboxed URL
            # to which it applies does, so caching it beyond the sanbox key
            # timeout is pointless.
            request.setHeader(b'Access-Control-Max-Age',
                              b'%d' % ArtifactSandbox.keyTimeout)

        # Reply without content.
        request.setResponseCode(204)
        request.setHeader(b'Content-Length', b'0')
        return b''

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
                ).render(request)

        if isinstance(node, ZipTreeNode):
            # Path ends at a directory.
            return self.renderDirectory(request, tree.zipFile, node)
        else:
            # Path ends at a file.
            return self.renderFile(request, tree.zipFile, node)

    def renderDirectory(self,
                        request: TwistedRequest,
                        zipFile: ZipFile,
                        node: 'ZipTreeNode'
                        ) -> object:
        """Serve a directory from a ZIP file.
        """

        # URLs for directory entries should end with a slash.
        if not request.path.endswith(b'/'):
            path = (request.postpath or request.prepath)[-1]
            return redirectTo(path + b'/', request)

        # Serve index.html at directory URL.
        entries = node.children
        index = entries.get('index.html')
        if isinstance(index, ZipInfo):
            return self.renderFile(request, zipFile, index)

        # If a ZIP contains a single file or single top-level directory,
        # redirect to that.
        if len(request.postpath) == 1:
            if len(entries) == 1:
                (name, entry), = entries.items()
                path = name.encode()
                if isinstance(entry, ZipTreeNode):
                    path += b'/'
                return redirectTo(path, request)

        request.setResponseCode(500)
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
        return b'ZIP directory listing not yet implemented\n'

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
        request.setHeader(b'Content-Disposition', b'inline')

        # Serve data in compressed form if user agent accepts it.
        if info.compress_type == ZIP_DEFLATED:
            accept = AcceptedEncodings.parse(
                                        request.getHeader('accept-encoding'))
            decompress = 4.0 * accept['gzip'] < accept['identity']
            if not decompress:
                request.setHeader('Content-Encoding', 'gzip')
        else:
            decompress = True
        if decompress:
            FileProducer.servePlain(zipFile.open(info), request)
        else:
            FileProducer.serveZipEntry(self.zipPath.open(), info, request)
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
        super().__init__()
        self.children: Dict[str, Union[ZipTreeNode, ZipInfo]] = {}

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
                    raise ValueError(f'Duplicate file: "{info.filename}"')
                else:
                    raise ValueError(
                        f'File overlaps with directory: "{info.filename}"'
                        )
            else:
                # Directory entry.
                pass
        else:
            if child is None:
                children[name] = child = ZipTreeNode()
            elif isinstance(child, ZipInfo):
                raise ValueError(
                    f'File overlaps with directory: "{child.filename}"'
                    )
            child.add(nextName, remainder, info)

class ZipTree:
    cache: Dict[str, Tuple['ZipTree', IDelayedCall]] = {}
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
        super().__init__()
        self.zipFile = zipFile
        self.root = ZipTreeNode.build(zipFile)

    def find(self, segments: Iterable[str]) -> Union[ZipInfo, ZipTreeNode]:
        """Look up a file path in this ZIP directory tree.
        Return a ZipInfo if a file is found.
        Return a ZipTreeNode if a directory is found.
        Raise KeyError if no match is found.
        """
        node: Union[ZipInfo, ZipTreeNode] = self.root
        for segment in segments:
            if isinstance(node, ZipTreeNode):
                if segment:
                    node = node.children[segment]
            else:
                raise KeyError(segment)
        return node

def populateArtifacts(parent: Resource,
                      baseDir: Path,
                      anonOperator: bool,
                      dependencies: Mapping[str, Any]
                      ) -> None:
    """Add resources for storing and retrieving artifacts under the given
    parent resource.
    """
    path = FilePath(str(baseDir))
    sandbox = ArtifactSandbox(path)
    parent.putChild(b'sandbox', sandbox)
    auth = ArtifactAuthWrapper(sandbox.rootPath.child('jobs'),
                               anonOperator,
                               dependencies['tokenDB'])
    parent.putChild(b'jobs', auth)

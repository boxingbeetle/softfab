# SPDX-License-Identifier: BSD-3-Clause

from gzip import GzipFile
from mimetypes import guess_type
from os import fsync, replace
from typing import cast

from twisted.python.filepath import FilePath, InsecurePath
from twisted.web.http import Request as TwistedRequest
from twisted.web.resource import IResource, Resource
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
        gzipPath = self.baseDir.child(segment + '.gz')
        if gzipPath.isfile():
            return GzippedArtifact(gzipPath, asIs=False)

        if segment.endswith('.gz'):
            gzipPath = self.baseDir.child(segment)
            if request.method == b'PUT' or gzipPath.isfile():
                return GzippedArtifact(gzipPath, asIs=True)

        if request.method == b'PUT':
            return ClientErrorResource('Uploads must use gzip format')
        else:
            return NotFoundResource(
                'No artifact named "%s" exists for this task' % segment
                )

    def renderIndex(self, request: TwistedRequest) -> bytes:
        return b'Listing task subresources is not implemented yet'

class GzippedArtifact(Resource):
    """Single-file artifact stored as gzip file."""

    def __init__(self, path: FilePath, *, asIs: bool):
        super().__init__()
        self.path = path
        self.asIs = asIs

    def getChild(self, path: bytes, request: TwistedRequest) -> Resource:
        return NotFoundResource(
            'Artifact "%s" cannot not contain subitems'
            % request.prepath[-2].decode()
            )

    def render_GET(self, request: TwistedRequest) -> bytes:
        path = self.path

        if self.asIs:
            request.setHeader(b'Content-Type', b'application/gzip')
        else:
            contentType, contentEncoding = guess_type(path.basename(),
                                                      strict=False)
            if contentType is None:
                contentType = 'application/octet-stream'
            request.setHeader(b'Content-Type', contentType.encode())
            if contentEncoding is not None:
                # TODO: Check for gzip in the Accept-Encoding header.
                #       In practice though, gzip is accepted universally.
                request.setHeader(b'Content-Encoding', contentEncoding.encode())

        # TODO: Supply the data using a producer instead of all at once.
        return path.getContent()

    def render_PUT(self, request: TwistedRequest) -> bytes:
        path = self.path
        if path.isfile():
            request.setResponseCode(409)
            request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
            return b'Artifacts cannot be overwritten\n'

        # We currently only support upload of already-compressed files.
        assert self.asIs

        # Note: Twisted buffers the entire upload into 'request.content'
        #       prior to calling our render method.
        #       There doesn't seem to be a clean way to handle streaming
        #       uploads in Twisted; we'd have to set site.requestFactory
        #       to a request implementation that overrides gotLength() or
        #       handleContentChunk(), both of which are documented as
        #       "not intended for users".

        # Process large files in chunks.
        # TODO: Return control to the Twisted reactor inbetween chunks.
        #       Or maybe deferToThread() is a better approach, since that
        #       also deals with fsync() potentially taking a long time.
        blockSize = 16384

        # Verify that the uploaded file is a valid gzip file.
        # This will also catch truncated uploads.
        content = request.content
        try:
            with GzipFile(fileobj=content) as gz:
                while True:
                    data = gz.read(blockSize)
                    if not data:
                        break
        except (OSError, EOFError) as ex:
            request.setResponseCode(415)
            request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
            return b'Uploaded data is not a valid gzip file: %s\n' % (
                str(ex).encode()
                )

        # Copy content.
        content.seek(0, 0)
        uploadPath = path.siblingExtension('.part')
        inp = request.content
        path.parent().makedirs(ignoreExistingDirectory=True)
        out = uploadPath.open('wb')
        try:
            while True:
                data = inp.read(blockSize)
                if not data:
                    break
                out.write(data)
            out.flush()
            fsync(out.fileno())
        finally:
            out.close()
        replace(uploadPath.path, path.path)
        path.changed()

        request.setResponseCode(201)
        return b'Artifact stored\n'

def createArtifactRoot(baseDir: str, anonOperator: bool) -> IResource:
    path = FilePath(baseDir)
    return ArtifactAuthWrapper(path, anonOperator)

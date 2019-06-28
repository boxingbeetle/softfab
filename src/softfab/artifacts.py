# SPDX-License-Identifier: BSD-3-Clause

from mimetypes import guess_type
from typing import cast

from twisted.python.filepath import FilePath, InsecurePath
from twisted.web.http import Request as TwistedRequest
from twisted.web.resource import IResource, Resource
from zope.interface import implementer

from softfab.joblib import Job, jobDB
from softfab.projectlib import project
from softfab.request import Request
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
        message = 'Access denied: you do not have the necessary permissions'
        if ex.args:
            message += ' to ' + cast(str, ex.args[0])
        return cls(message)

class NotFoundResource(ClientErrorResource):
    code = 404

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
            return self.childForSegment(segment)
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

    def childForSegment(self, segment: str) -> Resource:
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
        checkPrivilege(self.user, 'j/l', 'list jobs')

    def childForSegment(self, segment: str) -> Resource:
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

    def childForSegment(self, segment: str) -> Resource:
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
        # TODO: Our privilege system is too fine grained.
        checkPrivilege(self.user, 'j/a', 'access jobs')
        checkPrivilege(self.user, 't/l', 'list tasks')

    def childForSegment(self, segment: str) -> Resource:
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
        checkPrivilege(self.user, 't/a', 'access tasks')

    def childForSegment(self, segment: str) -> Resource:
        gzipPath = self.baseDir.child(segment + '.gz')
        if gzipPath.isfile():
            return GzippedArtifact(gzipPath)
        return NotFoundResource(
            'No "%s" subitem exists for tasks' % segment
            )

    def renderIndex(self, request: TwistedRequest) -> bytes:
        return b'Listing task subresources is not implemented yet'

class GzippedArtifact(Resource):
    """Single-file artifact stored as gzip file."""

    def __init__(self, path: FilePath):
        super().__init__()
        self.path = path

    def getChild(self, path: bytes, request: TwistedRequest) -> Resource:
        return NotFoundResource(
            'Artifact "%s" does not contain subitems'
            % request.prepath[-2].decode()
            )

    def render_GET(self, request: TwistedRequest) -> bytes:
        path = self.path
        contentType, contentEncoding = guess_type(path.basename(), strict=False)
        if contentType is None:
            contentType = 'application/octet-stream'
        request.setHeader(b'Content-Type', contentType.encode())
        if contentEncoding is not None:
            # TODO: Check for gzip in the Accept-Encoding header.
            #       In practice though, gzip is accepted universally.
            request.setHeader(b'Content-Encoding', contentEncoding.encode())
        # TODO: Supply the data using a producer instead of all at once.
        return path.getContent()

def createArtifactRoot(baseDir: str, anonOperator: bool) -> IResource:
    path = FilePath(baseDir, alwaysCreate=True)
    return ArtifactAuthWrapper(path, anonOperator)

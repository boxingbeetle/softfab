# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum, auto
from logging import Logger
from types import ModuleType
from typing import Any, Callable, Iterator, Optional
import json
import logging

from twisted.web.resource import Resource
from twisted.web.server import Request as TwistedRequest

from softfab.request import RequestBase
from softfab.resourcelib import ResourceDB
from softfab.restypelib import repoResourceTypeName
from softfab.schedulelib import ScheduleDB
from softfab.utils import iterModules


class WebhookEvents(Enum):
    PING = auto()
    PUSH = auto()
    UNSUPPORTED = auto()

class WebhookResource(Resource):

    resourceDB: ResourceDB
    scheduleDB: ScheduleDB

    def __init__(self, name: str, webhook: ModuleType):
        super().__init__()
        self.name = name
        self.getEvent: Callable[[TwistedRequest], WebhookEvents] = \
                getattr(webhook, 'getEvent')
        self.verifySignature: Callable[[TwistedRequest, bytes, bytes], bool] = \
                getattr(webhook, 'verifySignature')
        self.findRepositoryURLs: Callable[[object], Iterator[str]] = \
                getattr(webhook, 'findRepositoryURLs')
        self.findBranches: Callable[[object], Iterator[str]] = \
                getattr(webhook, 'findBranches')

    def render_POST(self, request: TwistedRequest) -> bytes:
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')

        # Is this an event we're interested in?
        event = self.getEvent(request)
        if event is WebhookEvents.UNSUPPORTED:
            return b'Unsupported event ignored\n'

        # Parse Content-Type header.
        req = RequestBase(request)
        contentType, contentTypeParams = req.contentType
        if contentType != 'application/json':
            request.setResponseCode(415)
            if contentType is None:
                return b'No Content-Type specified\n'
            else:
                return b'Unsupported Content-Type; expected application/json\n'
        assert contentTypeParams is not None

        # Decode content.
        # JSON must be encoded as UTF-8 without a BOM.
        #   https://tools.ietf.org/html/rfc8259#section-8.1
        charset = contentTypeParams.get('charset', 'UTF-8')
        if charset.casefold() != 'utf-8':
            request.setResponseCode(415)
            return b'Unsupported charset "%s", please use UTF-8 instead\n' \
                   % charset.encode()
        contentBytes = req.rawInput().read()
        content = contentBytes.decode()
        if content.startswith('\ufeff'):
            content = content[1:]

        # Parse JSON.
        try:
            parsed = json.loads(content)
        except ValueError as ex:
            request.setResponseCode(400)
            return b'Invalid JSON: %s\n' % str(ex).encode()

        # Find repository.
        # We compare URLs case-insensitive. In general, URL paths could be
        # case-sensitive, but all hosting platforms I've tested either ignore
        # case (GitHub, Gogs) or redirect to all lower case (GitLab, Bitbucket).
        try:
            repoURLs = set(
                url.casefold()
                for url in self.findRepositoryURLs(parsed)
                )
        except KeyError as ex:
            request.setResponseCode(400)
            return b'Missing key in JSON: %s\n' % str(ex).encode()
        repoMatch = None
        resourceDB = self.resourceDB
        for repoId in resourceDB.resourcesOfType(repoResourceTypeName):
            repo = resourceDB[repoId]
            locator = repo.getParameter('locator')
            if locator is not None and locator.casefold() in repoURLs:
                repoMatch = repo

        # Authenticate.
        # Use the same flow as much as possible to make timing attacks harder.
        errorMessage: Optional[str] = None
        secret = 'dummysecret'
        if repoMatch is None:
            errorMessage = 'no repository matches given URL(s)'
        else:
            secretParam = repoMatch.getParameter('secret')
            if secretParam is None:
                errorMessage = 'no secret has been set for repository'
            else:
                secret = secretParam
        if not self.verifySignature(request, contentBytes, secret.encode()):
            if errorMessage is None:
                errorMessage = 'signature mismatch'
        if errorMessage is not None:
            logging.warning('Ignoring callback on "%s" webhook: %s',
                            self.name, errorMessage)
            request.setResponseCode(403)
            return b'Could not authenticate this callback.\n' \
                   b'See Control Center log for details.\n'
        assert repoMatch is not None

        if event is WebhookEvents.PING:
            return self.handlePing()
        elif event is WebhookEvents.PUSH:
            return self.handlePush(request, repoMatch.getId(), parsed)
        else:
            # https://github.com/PyCQA/pylint/issues/2908
            raise AssertionError(event)

    def handlePing(self) -> bytes:
        return (
            b'Pong!\n'
            b'\n'
            b'Ping was received, parsed, matched to a repository '
            b'and authenticated.\n'
            )

    def handlePush(self,
                   request: TwistedRequest,
                   repoId: str,
                   parsed: Any
                   ) -> bytes:
        # Find branches.
        try:
            branches = set(self.findBranches(parsed))
        except KeyError as ex:
            request.setResponseCode(400)
            return b'Missing key in JSON: %s\n' % str(ex).encode()

        # Trigger schedules.
        tagValues = {f'{repoId}/{branch}' for branch in branches}
        scheduleIds = []
        for scheduleId, schedule in self.scheduleDB.items():
            if tagValues & schedule.tags.getTagValues('sf.trigger'):
                schedule.setTrigger()
                scheduleIds.append(scheduleId)

        logging.info('Got update on "%s" webhook for branch: %s; '
                     'triggered schedule: %s',
                     self.name, ', '.join(branches), ', '.join(scheduleIds))
        return b'Received\n'

class WebhookIndexResource(Resource):

    def render_GET(self, request: TwistedRequest) -> bytes:
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
        return b'\n'.join(sorted(self.children)) + b'\n'

def createWebhooks(log: Logger,
                   injector: Callable[[Resource], None]
                   ) -> Resource:
    index = WebhookIndexResource()
    for name, module in iterModules(__name__, log):
        try:
            resource = WebhookResource(name, module)
            injector(resource)
        except AttributeError as ex:
            log.error('Error creating webhook: %s', ex)
        else:
            index.putChild(name.encode(), resource)
    return index

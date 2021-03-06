# SPDX-License-Identifier: BSD-3-Clause

"""Functions for accessing the SoftFab API."""

from cgi import parse_header
from typing import Awaitable, Optional, Tuple, TypeVar

from twisted.internet.defer import Deferred, ensureDeferred, succeed
from twisted.internet.interfaces import IConsumer, IReactorCore
from twisted.python.failure import Failure
from twisted.web.client import Response, readBody
from twisted.web.http_headers import Headers
from twisted.web.iweb import IAgent, IBodyProducer
from zope.interface import implementer


@implementer(IBodyProducer)
class SmallBodyProducer:
    """Produces a request body from a L{bytes} sequence.

    This can be used for efficiently sending small requests.
    """

    def __init__(self, data: bytes):
        self._data = data
        self.length = len(data)

    def startProducing(self, consumer: IConsumer) -> Deferred:
        consumer.write(self._data)
        return succeed(None)

    def stopProducing(self) -> None:
        pass

    def pauseProducing(self) -> None:
        pass

    def resumeProducing(self) -> None:
        pass

async def _runRequest(agent: IAgent,
                      url: str,
                      method: bytes,
                      payload: Optional[bytes] = None
                      ) -> Tuple[Response, bytes]:
    """Make an HTTP request.
    All buffering is done in-memory, so this function should only be used
    for requests with a small payload and a small reply body.
    """

    headers = Headers()
    if payload is None:
        bodyProducer = None
    else:
        bodyProducer = SmallBodyProducer(payload)
        headers.addRawHeader('Content-Type', 'application/json; charset=UTF-8')
    response = await agent.request(method, url.encode(), headers, bodyProducer)

    # Note: We read the full body even if we're not going to decode it,
    #       to make sure the connection will be closed.
    #       We could do the same with a custom Protocol, but that is
    #       a lot of work for a situation that should never occur.
    body = await readBody(response)

    if response.code != 204:
        contentTypeHeaders = response.headers.getRawHeaders('Content-Type')
        if not contentTypeHeaders:
            raise OSError("Response lacks Content-Type header")
        contentType, contentTypeParams = parse_header(contentTypeHeaders[0])
        if contentType not in ('application/json', 'text/plain'):
            raise OSError(f"Response has unsupported content type: "
                          f"{contentType}")
        if contentTypeParams.get('charset', 'utf-8').lower() != 'utf-8':
            raise OSError("Response not encoded in UTF-8")

    return response, body

async def run_GET(agent: IAgent, url: str) -> bytes:
    """Make an HTTP GET request."""

    response, body = await _runRequest(agent, url, b'GET')

    code = response.code
    if code == 200:
        return body
    else:
        phrase = response.phrase.decode(errors='replace')
        message = body.decode(errors='replace').rstrip()
        raise OSError(f"Unexpected result from HTTP GET: {code} {phrase}\n"
                      f"{message}")

async def run_PUT(agent: IAgent, url: str, payload: bytes) -> bytes:
    """Make an HTTP PUT request."""

    response, body = await _runRequest(agent, url, b'PUT', payload)

    code = response.code
    if code in (200, 201, 204):
        return body
    else:
        phrase = response.phrase.decode(errors='replace')
        message = body.decode(errors='replace').rstrip()
        raise OSError(f"Unexpected result from HTTP PUT: {code} {phrase}\n"
                      f"{message}")

async def run_PATCH(agent: IAgent, url: str, payload: bytes) -> bytes:
    """Make an HTTP PATCH request."""

    response, body = await _runRequest(agent, url, b'PATCH', payload)

    code = response.code
    if code in (200, 204):
        return body
    else:
        phrase = response.phrase.decode(errors='replace')
        message = body.decode(errors='replace').rstrip()
        raise OSError(f"Unexpected result from HTTP PATCH: {code} {phrase}\n"
                      f"{message}")

async def run_DELETE(agent: IAgent, url: str) -> None:
    """Make an HTTP DELETE request."""

    response, body = await _runRequest(agent, url, b'DELETE')

    code = response.code
    if code not in (200, 202, 204):
        phrase = response.phrase.decode(errors='replace')
        message = body.decode(errors='replace').rstrip()
        raise OSError(f"Unexpected result from HTTP DELETE: {code} {phrase}\n"
                      f"{message}")

T = TypeVar('T')

def runInReactor(reactor: IReactorCore, call: Awaitable[T]) -> T:

    def run() -> None:
        ensureDeferred(call).addCallbacks(done, failed)

    output: T

    def done(result: T) -> None:
        nonlocal output
        output = result
        reactor.stop()

    failure: Optional[Failure] = None

    def failed(reason: Failure) -> None:
        nonlocal failure
        failure = reason
        reactor.stop()

    reactor.callWhenRunning(run)
    reactor.run()
    if failure is not None:
        failure.raiseException()
    try:
        return output
    except UnboundLocalError:
        # The reactor returned without succeeding or failing.
        raise OSError('Aborted')

# SPDX-License-Identifier: BSD-3-Clause

"""Functions for accessing the SoftFab API."""

from cgi import parse_header
from io import BytesIO
from typing import Awaitable, Optional, Tuple, TypeVar

from twisted.internet.defer import ensureDeferred
from twisted.python.failure import Failure
from twisted.web.client import Agent, FileBodyProducer, Response, readBody
from twisted.web.http_headers import Headers
from twisted.web.iweb import IAgentEndpointFactory


async def _runRequest(endpointFactory: IAgentEndpointFactory,
                      url: str,
                      method: bytes,
                      payload: Optional[bytes] = None
                      ) -> Tuple[Response, bytes]:
    """Make an HTTP request.
    All buffering is done in-memory, so this function should only be used
    for requests with a small payload and a small reply body.
    """

    # pylint: disable=import-outside-toplevel
    from softfab.reactor import reactor

    agent = Agent.usingEndpointFactory(reactor, endpointFactory)

    headers = Headers()
    if payload is None:
        bodyProducer = None
    else:
        bodyProducer = FileBodyProducer(BytesIO(payload))
        headers.addRawHeader('Content-Type', 'application/json; charset=UTF-8')
    response = await agent.request(method, url.encode(), headers, bodyProducer)

    # Note: We read the full body even if we're not going to decode it,
    #       to make sure the connection will be closed.
    #       We could do the same with a custom Protocol, but that is
    #       a lot of work for a situation that should never occur.
    body = await readBody(response)

    contentTypeHeaders = response.headers.getRawHeaders('Content-Type')
    if not contentTypeHeaders:
        raise OSError("Response lacks Content-Type header")
    contentType, contentTypeParams = parse_header(contentTypeHeaders[0])
    if contentType not in ('application/json', 'text/plain'):
        raise OSError(f"Response has unsupported content type: {contentType}")
    if contentTypeParams.get('charset', 'utf-8').lower() != 'utf-8':
        raise OSError("Response not encoded in UTF-8")

    return response, body

async def run_GET(endpointFactory: IAgentEndpointFactory, url: str) -> bytes:
    """Make an HTTP GET request."""

    response, body = await _runRequest(endpointFactory, url, b'GET')

    code = response.code
    if code == 200:
        return body
    else:
        phrase = response.phrase.decode(errors='replace')
        message = body.decode(errors='replace').rstrip()
        raise OSError(f"Unexpected result from HTTP GET: {code} {phrase}\n"
                      f"{message}")

async def run_PUT(endpointFactory: IAgentEndpointFactory,
                  url: str,
                  payload: bytes
                  ) -> None:
    """Make an HTTP PUT request."""

    response, body = await _runRequest(endpointFactory, url, b'PUT', payload)

    code = response.code
    if code not in (200, 201, 204):
        phrase = response.phrase.decode(errors='replace')
        message = body.decode(errors='replace').rstrip()
        raise OSError(f"Unexpected result from HTTP PUT: {code} {phrase}\n"
                      f"{message}")

async def run_DELETE(endpointFactory: IAgentEndpointFactory, url: str) -> None:
    """Make an HTTP DELETE request."""

    response, body = await _runRequest(endpointFactory, url, b'DELETE')

    code = response.code
    if code not in (200, 202, 204):
        phrase = response.phrase.decode(errors='replace')
        message = body.decode(errors='replace').rstrip()
        raise OSError(f"Unexpected result from HTTP DELETE: {code} {phrase}\n"
                      f"{message}")

T = TypeVar('T')

def runInReactor(call: Awaitable[T]) -> T:
    # pylint: disable=import-outside-toplevel
    from softfab.reactor import reactor

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
    return output

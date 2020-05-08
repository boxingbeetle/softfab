# SPDX-License-Identifier: BSD-3-Clause

"""Functions for accessing the SoftFab API."""

from cgi import parse_header
from typing import Awaitable, Optional, TypeVar

from twisted.internet.defer import ensureDeferred
from twisted.python.failure import Failure
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from twisted.web.iweb import IAgentEndpointFactory


async def run_GET(endpointFactory: IAgentEndpointFactory, url: str) -> bytes:
    """Make an HTTP GET request."""

    # pylint: disable=import-outside-toplevel
    from twisted.internet import reactor

    agent = Agent.usingEndpointFactory(reactor, endpointFactory)

    headers = Headers()
    response = await agent.request(b'GET', url.encode(), headers, None)

    contentTypeHeaders = response.headers.getRawHeaders('Content-Type')
    if not contentTypeHeaders:
        raise OSError("Response lacks Content-Type header")
    contentType, contentTypeParams = parse_header(contentTypeHeaders[0])
    if contentType not in ('application/json', 'text/plain'):
        raise OSError(f"Response has unsupported content type: {contentType}")
    if contentTypeParams.get('charset', 'utf-8').lower() != 'utf-8':
        raise OSError("Response not encoded in UTF-8")

    body = await readBody(response)

    code = response.code
    if code == 200:
        return body
    else:
        phrase = response.phrase.decode(errors='replace')
        message = body.decode(errors='replace').rstrip()
        raise OSError(f"Unexpected result from HTTP GET: {code} {phrase}\n"
                      f"{message}")

T = TypeVar('T')

def runInReactor(call: Awaitable[T]) -> T:
    # pylint: disable=import-outside-toplevel
    from twisted.internet import reactor

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
    if failure is None:
        return output
    else:
        failure.raiseException()
        # Neither pylint nor mypy knows that raiseException() does not return.
        assert False
        return None

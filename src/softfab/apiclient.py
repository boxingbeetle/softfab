# SPDX-License-Identifier: BSD-3-Clause

"""Functions for accessing the SoftFab API."""

from io import BytesIO
from typing import Awaitable, Optional, TypeVar

from twisted.internet.defer import ensureDeferred
from twisted.internet.interfaces import IStreamClientEndpoint
from twisted.python.failure import Failure
from twisted.web.client import HTTPDownloader


class Buffer(BytesIO):
    """A byte buffer that remembers its contents when it is closed."""
    value: Optional[bytes] = None

    def close(self) -> None:
        self.value = self.getvalue()
        super().close()

async def run_GET(endpoint: IStreamClientEndpoint, url: str) -> bytes:
    """Make an HTTP GET request."""

    buffer = Buffer()
    factory = HTTPDownloader(url.encode(), buffer)
    await endpoint.connect(factory)

    await factory.deferred
    status = int(factory.status)
    if status == 200:
        data = buffer.value
        assert data is not None
        return data
    else:
        message = factory.message.decode()
        raise OSError(f"Unexpected result from HTTP GET: {status} {message}")

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

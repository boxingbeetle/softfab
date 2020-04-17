# SPDX-License-Identifier: BSD-3-Clause

"""Functions for accessing the SoftFab API."""

from io import BytesIO
from typing import Optional

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.interfaces import IStreamClientEndpoint
from twisted.web.client import HTTPDownloader


class Buffer(BytesIO):
    """A byte buffer that remembers its contents when it is closed."""
    value: Optional[bytes] = None

    def close(self) -> None:
        self.value = self.getvalue()
        super().close()

@inlineCallbacks
def run_GET(endpoint: IStreamClientEndpoint, url: str) -> Deferred:
    """Make an HTTP GET request."""

    buffer = Buffer()
    factory = HTTPDownloader(url.encode(), buffer)
    yield endpoint.connect(factory)

    yield factory.deferred
    status = int(factory.status)
    if status == 200:
        return buffer.value
    else:
        message = factory.message.decode()
        raise OSError(f"Unexpected result from HTTP GET: {status} {message}")

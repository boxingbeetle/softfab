# SPDX-License-Identifier: BSD-3-Clause

"""Functions for accessing the SoftFab API."""

from io import BytesIO
from typing import Optional

from twisted.internet.interfaces import IStreamClientEndpoint
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

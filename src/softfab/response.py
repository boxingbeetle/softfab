# SPDX-License-Identifier: BSD-3-Clause

from base64 import standard_b64encode
from gzip import GzipFile
from hashlib import md5
from io import BytesIO
from typing import Optional, Union

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.python.failure import Failure
from twisted.web.http import CACHED
from twisted.web.iweb import IRequest

from softfab.TwistedUtil import getRelativeRoot
from softfab.compat import NoReturn
from softfab.useragent import AcceptedEncodings, UserAgent
from softfab.utils import IllegalStateError
from softfab.xmlgen import XMLContent, adaptToXML


def createETag(data: bytes) -> bytes:
    """Return a content hash for the given data, encoded in ASCII."""
    return standard_b64encode(md5(data).digest()).rstrip(b'=')

_fileNameTranslation = bytes(
    ch if 32 <= ch < 127 and ch not in b'"\\%?' else ord(b'_')
    for ch in range(256)
    )
"""Lookup table for `bytes.translate()` that maps characters that we cannot
include in a "filename=" parameter to underscores.
For interoperability, we cannot use backslashes escapes, which makes it
impossible to produce a double quote and the backslash itself.
We reject the percent character for interoperability as well.
The question mark is rejected because that is what the 'replace' encoding
error policy maps non-ASCII characters to.
"""

def _encodeHeaderValue(key: bytes, value: str) -> bytes:
    """Encodes a string that is used in the value part of the
    Content-Disposition HTTP header.
    """

    # We follow the advice from RFC-6266 appendix D.
    #   https://tools.ietf.org/html/rfc6266#appendix-D

    # Build an ASCII representation.
    asciiValue = value.encode('ascii', 'replace')

    # Filter out characters we cannot use in quoted-string form.
    filteredAscii = asciiValue.translate(_fileNameTranslation)

    # If ASCII is sufficient, include only that.
    # Note that '?' replacements from encoding were translated to '_'.
    if filteredAscii == asciiValue:
        return b'%b="%b"' % (key, asciiValue)

    # Encode string as UTF-8, then encode bytes with percent encoding.
    utf8Value = value.encode()
    encoded = b''.join(
        ch if ch.isalnum() or ch in b'!#$&+-.^_`|~' else b'%%%02X' % ord(ch)
        for ch in (utf8Value[idx:idx+1] for idx in range(len(utf8Value)))
        )

    # Provide the UTF-8 and the ASCII version as a fallback.
    return b'''%b="%b"; %b*=UTF-8''%b''' % (key, filteredAscii, key, encoded)

class NotModified(Exception):
    """Raised when we can skip writing the response body because
    the user agent already has an up-to-date version of the resource.
    """

class ResponseHeaders:

    def __init__(self,
                 request: IRequest,
                 frameAncestors: str,
                 userAgent: UserAgent):
        super().__init__()

        self._request = request
        self._frameAncestors = frameAncestors
        self.userAgent = userAgent

        # Determine whether or not we will gzip the body.
        # We prefer gzip to save on bandwidth.
        accept = AcceptedEncodings.parse(request.getHeader('accept-encoding'))
        self._gzipContent = 2.0 * accept['gzip'] > accept['identity']

    def allowEmbedding(self) -> None:
        """Allow embedding of this resource on the current site.
        This is necessary to display SVGs in <object> tags.
        """
        frameAncestors = self._frameAncestors
        if frameAncestors == "'none'":
            self._frameAncestors = "'self'"
        elif "'self'" not in frameAncestors:
            self._frameAncestors = f"'self' {frameAncestors}"

    def setStatus(self, code: int, msg: Optional[str] = None) -> None:
        self._request.setResponseCode(
            code,
            None if msg is None else msg.encode('ascii', 'ignore')
            )

    def setContentType(self, value: str) -> None:
        self._request.setHeader('content-type', value.encode('ascii'))
        # Do not compress data that is already compressed.
        if value == 'image/png':
            self._gzipContent = False

    def setHeader(self, name: str, value: str) -> None:
        self._request.setHeader(name.lower(), value.encode('ascii', 'ignore'))

    def setFileName(self, fileName: str) -> None:
        '''Suggest a file name to the browser for saving this document.
        This method sets an HTTP header, so call it before you do any output.
        To be compatible with IE's lack of proper mime type handling,
        it is recommended to use a file name extension that implies the
        desired mime type.
        '''
        self._request.setHeader(
            'content-disposition',
            b'attachment; ' + _encodeHeaderValue(b'filename', fileName)
            )

    def sendRedirect(self, url: str) -> None:
        # Relative URLs must include page name: although a relative URL
        # containing only a query is valid, it is resolved to the parent of
        # the current page, which is not what we want.
        assert not url.startswith('?'), 'page is missing from URL'
        # Set HTTP headers for redirect.
        # Response code 303 specifies the way most existing clients incorrectly
        # handle 302 (see RFC-2616 section 10.3.3).
        self.setStatus(303)
        # RFC-7231 section 7.1.2 allows relative URLs in the Location header.
        request = self._request
        location = getRelativeRoot(request) + url
        request.setHeader('location', location.encode())

class Response(ResponseHeaders):

    def __init__(self,
                 request: IRequest,
                 frameAncestors: str,
                 userAgent: UserAgent):
        super().__init__(request, frameAncestors, userAgent)

        # Present entire page before deciding whether and how to send it
        # to the client.
        self.__buffer = BytesIO()
        self.__writeBytes = self.__buffer.write

        self.__connectionLostFailure: Optional[Failure] = None
        d = request.notifyFinish()
        d.addErrback(self.__connectionLost)

    def setETag(self, etag: bytes) -> None:
        """Set the given entity tag for this response.
        Raise NotModified if the tag matches an If-None-Match request header.
        """
        if self._gzipContent:
            # Since encoding the content with gzip changes it, we have to
            # return a different ETag if we use gzip.
            etag += b'-gzip'
        if self._request.setETag(etag) is CACHED:
            raise NotModified()

    def finish(self) -> None:
        request = self._request

        request.setHeader(
            'Content-Security-Policy',
            f"default-src 'self'; "
            f"form-action 'self'; "
            f"frame-src http: https:; "
            f"script-src 'self' 'unsafe-inline'; "
            f"style-src 'self' 'unsafe-inline'; "
            f"frame-ancestors {self._frameAncestors}"
            )

        # Tell cache that this is private data and that it can be cached,
        # but must be revalidated every time.
        request.setHeader(
            'Cache-Control', 'private, must-revalidate, max-age=0'
            )

        body = self.__buffer.getvalue()
        self.__buffer.close()
        # Any write attempt after this is an error.
        self.__writeBytes = writeAfterFinish

        if not request.etag:
            # Create entity tag from response body.
            try:
                self.setETag(createETag(body))
            except NotModified:
                # ETag match; no body should be written.
                return

        if self._gzipContent:
            request.setHeader('Content-Encoding', 'gzip')
            # Note: Some quick measurements show that compression level 6 gives
            #       a good balance between resulting size and CPU power needed.
            with GzipFile(None, 'wb', 6, request) as zfile:
                zfile.write(body)
        else:
            request.write(body)

    def __connectionLost(self, reason: Failure) -> None:
        self.__connectionLostFailure = reason

    def returnToReactor(self) -> Deferred:
        '''A page that writes a large response can hog the reactor for quite
        some time, during which other requests are not serviced. To prevent
        this, a large response should be cut into chunks and control should be
        returned to the reactor inbetween chunks.
        Returns a Deferred that succeeds with no arguments if the client is
        still connected, or fails with a ConnectionLost if the client
        disconnected.

        Example use:
            async def writeReply(self, response, proc):
                for chunk in chop(proc.records, 1000):
                    response.writeXML(record.format() for record in chunk)
                    await response.returnToReactor()
        '''
        d = Deferred()
        reactor.callLater(0, self.__resume, d)
        return d

    def __resume(self, d: Deferred) -> None:
        """Helper method for `returnToReactor()`."""
        lost = self.__connectionLostFailure
        if lost is None:
            d.callback(None)
        else:
            d.errback(lost)

    def write(self, text: Union[None, bytes, str]) -> None:
        if isinstance(text, str):
            self.__writeBytes(text.encode())
        elif isinstance(text, bytes):
            self.__writeBytes(text)
        elif text is not None:
            raise TypeError(
                f'Cannot handle document output '
                f'of type "{type(text).__name__}"'
                )

    def writeXML(self, xml: XMLContent) -> None:
        """Append the given XML content to this reponse.
        """
        self.__writeBytes(adaptToXML(xml).flattenXML().encode())

def writeAfterFinish(buffer: Union[bytes, bytearray]) -> NoReturn:
    raise IllegalStateError('Write on finished response')

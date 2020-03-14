# SPDX-License-Identifier: BSD-3-Clause

from base64 import standard_b64encode
from gzip import GzipFile
from hashlib import md5
from io import BytesIO
from typing import Callable, Optional, Union

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.interfaces import IProducer, IPullProducer, IPushProducer
from twisted.python.failure import Failure
from twisted.web.http import CACHED
from twisted.web.iweb import IRequest
from twisted.web.server import NOT_DONE_YET

from softfab.compat import NoReturn
from softfab.projectlib import project
from softfab.useragent import AcceptedEncodings, UserAgent
from softfab.utils import IllegalStateError
from softfab.xmlgen import XMLContent, adaptToXML
import softfab.config


class Response:

    def __init__(self,
                 request: IRequest,
                 userAgent: UserAgent,
                 streaming: bool):
        self.__request = request
        self.__frameAncestors = project.frameAncestors
        self.userAgent = userAgent

        if streaming:
            # Streaming pages must not be buffered.
            self.__buffer = None
            self.__writeBytes: Callable[[Union[bytes, bytearray]], int] = \
                    request.write
        else:
            # Present entire page before deciding whether and how to send it
            # to the client.
            self.__buffer = BytesIO()
            self.__writeBytes = self.__buffer.write

        # Determine whether or not we will gzip the body.
        # We prefer gzip to save on bandwidth.
        accept = AcceptedEncodings.parse(request.getHeader('accept-encoding'))
        self.__gzipContent = 2.0 * accept['gzip'] > accept['identity']

        self.__producerDone: Optional[Deferred] = None

        self.__connectionLostFailure: Optional[Failure] = None
        d = request.notifyFinish()
        d.addErrback(self.__connectionLost)

    @property
    def rootURL(self) -> str:
        """Public root URL of this Control Center."""
        return softfab.config.rootURL

    @property
    def relativeRoot(self) -> str:
        """Relative URL from the requested page to the site root.
        Ends in a slash when non-empty.
        """
        return '../' * (len(self.__request.prepath) - 1)

    def finish(self) -> None:
        request = self.__request

        request.setHeader(
            'Content-Security-Policy',
            f"default-src 'self'; "
            f"form-action 'self'; "
            f"frame-src http: https:; "
            f"script-src 'self' 'unsafe-inline'; "
            f"style-src 'self' 'unsafe-inline'; "
            f"frame-ancestors {self.__frameAncestors}"
            )

        if self.__buffer is None:
            # Body was not buffered; this is a stream.
            request.setHeader('Cache-Control', 'no-cache')
            return

        # Tell cache that this is private data and that it can be cached,
        # but must be revalidated every time.
        request.setHeader(
            'Cache-Control', 'private, must-revalidate, max-age=0'
            )

        body = self.__buffer.getvalue()
        self.__buffer.close()
        # Any write attempt after this is an error.
        self.__buffer = None
        self.__writeBytes = writeAfterFinish

        gzipContent = self.__gzipContent

        # Compute entity tag.
        # Since encoding the content with gzip changes it, we have to return
        # a different ETag if we use gzip. However, the gzip format contains
        # a timestamp, meaning that the compressed body will be different
        # even if the raw body did not change. Therefore we compute the ETag
        # on the raw body and appened a flag to it if we plan to gzip it.
        etag = standard_b64encode(md5(body).digest()).rstrip(b'=')
        if gzipContent:
            etag += b'-gzip'
        if request.setETag(etag) is CACHED:
            # ETag match; no body should be written.
            return

        if gzipContent:
            request.setHeader('Content-Encoding', 'gzip')
            # Note: Some quick measurements show that compression level 6 gives
            #       a good balance between resulting size and CPU power needed.
            with GzipFile(None, 'wb', 6, request) as zfile:
                zfile.write(body)
        else:
            request.write(body)

    def __connectionLost(self, reason: Failure) -> None:
        self.__connectionLostFailure = reason

    def registerProducer(self, producer: IProducer) -> Deferred:
        if IPushProducer.providedBy(producer):
            streaming = True
        elif IPullProducer.providedBy(producer):
            streaming = False
        else:
            raise TypeError(type(producer))
        self.__request.registerProducer(producer, streaming)
        self.__producerDone = d = Deferred()
        return d

    def unregisterProducer(self) -> None:
        assert self.__producerDone is not None, 'producer was never registered'
        self.__request.unregisterProducer()
        self.__producerDone.callback(None)

    def returnToReactor(self, result: object = None) -> object:
        '''A page that writes a large response can hog the reactor for quite
        some time, during which other requests are not serviced. To prevent
        this, a large response should be cut into chunks and control should be
        returned to the reactor inbetween chunks.
        Returns a Deferred that has the given result if the client is still
        connected, or a Failure wrapping ConnectionLost if the client
        disconnected.

        Example use:
            @inlineCallbacks
            def writeReply(self, response, proc):
                for chunk in chop(proc.records, 1000):
                    response.writeXML(record.format() for record in chunk)
                    yield response.returnToReactor()
        '''
        d = Deferred()

        def resume(resumeResult: object) -> None:
            assert resumeResult is result
            lost = self.__connectionLostFailure
            if lost is None:
                d.callback(resumeResult)
            else:
                d.errback(lost)

        reactor.callLater(0, resume, result)
        return NOT_DONE_YET        # Fixed ticket 448

    def setStatus(self, code: int, msg: Optional[str] = None) -> None:
        self.__request.setResponseCode(
            code,
            None if msg is None else msg.encode('ascii', 'ignore')
            )

    def __encodeHeaderValue(self, key: bytes, value: str) -> bytes:
        '''Encodes a string that is used in the value part of an HTTP header.
        If the string contains non-ASCII characters, this method does a best
        effort to encode it in a way the user agent might understand.
        In other words, if the string must absolutely not be mangled, just use
        ASCII and bypass this method completely.
        '''
        family = self.userAgent.family

        if family in ('Konqueror', 'Safari'):
            # Browser does not seem to accept any kind of escaping.
            # It does accept spaces without quoting.
            # Tested with:
            # - Konqueror 3.5.7
            # - Safari 3.1.2
            return key + b'=' + value.encode('ascii', 'ignore')

        encoded = b''
        for byte in value.encode('utf-8'):
            ch = bytes((byte,))
            if ch.isalnum() or ch in b'.,-_':
                encoded += ch
            else:
                encoded += b'%%%02X' % byte

        if family in ('MSIE', 'Chrome'):
            # Browser understands escaped UTF8, but does not support parameters
            # defined with "*=".
            return key + b'=' + encoded

        try:
            # Test if string contains non-ASCII characters.
            asciiValue = value.encode('ascii', 'strict')
        except UnicodeEncodeError:
            pass
        else:
            if b'"' not in asciiValue:
                # If the string contains nothing but ASCII, things are simple.
                return key + b'="' + asciiValue + b'"'

        # This is how RFC-2184 prescribes it.
        # Mozilla and Opera support this correctly.
        # And for other browsers... well, until we've actually tested them, we
        # don't know what kind of problems they have, so we might as well assume
        # they implement the spec correctly.
        return key + b"*=utf8'en'" + encoded

    def setContentType(self, value: str) -> None:
        self.__request.setHeader('content-type', value.encode('ascii'))
        # Do not compress data that is already compressed.
        if value == 'image/png':
            self.__gzipContent = False

    def setHeader(self, name: str, value: str) -> None:
        self.__request.setHeader(name.lower(), value.encode('ascii', 'ignore'))

    def allowEmbedding(self) -> None:
        """Allow embedding of this resource on the current site.
        This is necessary to display SVGs in <object> tags.
        """
        frameAncestors = self.__frameAncestors
        if frameAncestors == "'none'":
            self.__frameAncestors = "'self'"
        elif "'self'" not in frameAncestors:
            self.__frameAncestors = f"'self' {frameAncestors}"

    def setFileName(self, fileName: str) -> None:
        '''Suggest a file name to the browser for saving this document.
        This method sets an HTTP header, so call it before you do any output.
        To be compatible with IE's lack of proper mime type handling,
        it is recommended to use a file name extension that implies the
        desired mime type.
        '''
        self.__request.setHeader(
            'content-disposition',
            b'attachment; ' + self.__encodeHeaderValue(b'filename', fileName)
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
        self.__request.setHeader('location', url.encode())

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

    def writeAndFinish(self, result: Union[None, bytes, str]) -> None:
        self.write(result)
        self.finish()

def writeAfterFinish(buffer: Union[bytes, bytearray]) -> NoReturn:
    raise IllegalStateError('Write on finished response')

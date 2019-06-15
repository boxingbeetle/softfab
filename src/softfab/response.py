# SPDX-License-Identifier: BSD-3-Clause

from base64 import standard_b64encode
from gzip import GzipFile
from hashlib import md5
from io import BytesIO
from typing import AnyStr, Callable, Optional, Union
from urllib.parse import urljoin

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.interfaces import IPullProducer, IPushProducer
from twisted.python.failure import Failure
from twisted.web.http import CACHED
from twisted.web.iweb import IRequest
from twisted.web.server import NOT_DONE_YET

from softfab.projectlib import project
from softfab.useragent import AcceptedEncodings, UserAgent
from softfab.xmlgen import XMLContent, adaptToXML


class Response:

    def __init__(self,
                 request: IRequest,
                 userAgent: UserAgent,
                 streaming: bool):
        self.__request = request
        self.userAgent = userAgent

        if streaming:
            # Streaming pages must not be buffered.
            self.__buffer = None
            self.__writeBytes = request.write \
                    # type: Callable[[Union[bytes, bytearray]], int]
        else:
            # Present entire page before deciding whether and how to send it
            # to the client.
            self.__buffer = BytesIO()
            self.__writeBytes = self.__buffer.write

        self.__producerDone = None # type: Optional[Deferred]

        self.__connectionLostFailure = None # type: Optional[Failure]
        d = request.notifyFinish()
        d.addErrback(self.__connectionLost)

    @property
    def relativeRoot(self) -> str:
        """Relative URL from the requested page to the site root.
        Ends in a slash when non-empty.
        """
        return '../' * (self.__request.path.count(b'/') - 1)

    def finish(self) -> None:
        request = self.__request

        # Cache control was introduced in HTTP 1.1.
        cacheControl = request.clientproto != 'HTTP/1.0'

        if not cacheControl:
            # Play it safe and ask for no caching.
            request.setHeader('Pragma', 'no-cache')

        if self.__buffer is None:
            # Body was not buffered; this is a stream.
            if cacheControl:
                request.setHeader('Cache-Control', 'no-cache')
            return

        if cacheControl:
            # Tell cache that this is private data and that it can be cached,
            # but must be revalidated every time.
            request.setHeader(
                'Cache-Control', 'private, must-revalidate, max-age=0'
                )

        request.setHeader(
            'Content-Security-Policy',
            "default-src 'self'; "
            "form-action 'self'; "
            "frame-src http: https:; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "frame-ancestors %s" % project.frameAncestors
            )

        body = self.__buffer.getvalue()
        self.__buffer.close()
        # Any write attempt after this is an error.
        self.__buffer = None
        self.__writeBytes = None # type: ignore

        # Determine whether or not we will gzip the body.
        # We prefer gzip to save on bandwidth.
        accept = AcceptedEncodings.parse(
            self.__request.getHeader('accept-encoding')
            )
        gzipContent = 2.0 * accept['gzip'] > accept['identity']

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

    def registerProducer(self, producer: object) -> Deferred:
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

    def setHeader(self, name: str, value: str) -> None:
        self.__request.setHeader(name.lower(), value.encode('ascii', 'ignore'))

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
        # The Location header must have an absolute URL as its value (see
        # RFC-2616 section 14.30).
        urlBytes = urljoin(self.__request.prePathURL(), url.encode())
        # Set HTTP headers for redirect.
        # Response code 303 specifies the way most existing clients incorrectly
        # handle 302 (see RFC-2616 section 10.3.3).
        self.setStatus(303 if self.__request.clientproto == 'HTTP/1.1' else 302)
        self.__request.setHeader('location', urlBytes)

    def write(self, *texts: Optional[AnyStr]) -> None:
        writeBytes = self.__writeBytes
        for text in texts:
            if isinstance(text, str):
                writeBytes(text.encode())
            elif isinstance(text, bytes):
                writeBytes(text)
            elif text is None:
                continue
            else:
                raise TypeError(
                    'Cannot handle document output of type "%s"' % type(text)
                    )

    def writeXML(self, xml: XMLContent) -> None:
        """Append the given XML content to this reponse.
        """
        self.__writeBytes(adaptToXML(xml).flattenXML().encode())

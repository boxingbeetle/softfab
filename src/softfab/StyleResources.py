# SPDX-License-Identifier: BSD-3-Clause

from gzip import GzipFile
from io import BytesIO
from typing import Dict, Optional
import logging
import re

from pygments.formatters import (  # pylint: disable=no-name-in-module
    HtmlFormatter
)
from twisted.web.http import datetimeToString
from twisted.web.iweb import IRequest
from twisted.web.resource import Resource
from twisted.web.static import Data

from softfab import styles
from softfab.compat import importlib_resources
from softfab.timelib import getTime, secondsPerDay
from softfab.useragent import AcceptedEncodings
from softfab.webgui import Image, ShortcutIcon, StyleSheet, pngIcon, svgIcon


def _load(fileName: str) -> Optional[bytes]:
    try:
        return importlib_resources.read_binary(styles, fileName)
    except OSError as ex:
        logging.error('Error reading style resource "%s": %s', fileName, ex)
        return None

class _StyleResource(Data):

    def render(self, request: IRequest) -> bytes:
        # File expires a long time from now.
        # RFC-2616 section 14.21: "HTTP/1.1 servers SHOULD NOT send Expires
        # dates more than one year in the future."
        request.setHeader(
            'expires', datetimeToString(getTime() + 365 * secondsPerDay)
            )
        return super().render(request)

class _CompressedStyleResource(_StyleResource):

    def __init__(self, data: bytes, mediaType: str):
        super().__init__(data, mediaType)

        # Note: Because we only compress these resources once, we might as well
        #       do it with maximum compression.
        with BytesIO() as buf:
            with GzipFile(None, 'wb', 9, buf) as zfile:
                zfile.write(data)
            gzippedData = buf.getvalue()

        self.__gzippedResource = _StyleResource(gzippedData, mediaType)

    def render(self, request: IRequest) -> bytes:
        # Pick an encoding based on client and server preferences.
        # We strongly prefer gzip because we save on bandwidth and
        # have pre-compressed the resource.
        accept = AcceptedEncodings.parse(request.getHeader('accept-encoding'))
        if 4.0 * accept['gzip'] > accept['identity']:
            request.setHeader('Content-Encoding', 'gzip')
            return self.__gzippedResource.render(request)
        else:
            return super().render(request)

_reStyleImage = re.compile(r'url\((\w+\.png)\)')

def _compressableType(mediaType: str) -> bool:
    '''Returns True iff the given media type is suitable for compression.
    Compressing data twice only slows things down, so already compressed
    formats like PNG should not be compressed again, while text formats
    like CSS and XML should be compressed.
    '''
    return mediaType.startswith('text/') or mediaType.endswith('+xml')

class _StyleRoot(Resource):
    relativeURL = 'styles'

    def __init__(self) -> None:
        super().__init__()
        self.__icons: Dict[str, Image] = {}

    def __addFile(self, fileName: str, mediaType: str) -> Optional[bytes]:
        data = _load(fileName)
        if data is not None:
            resourceFactory = (
                _CompressedStyleResource
                if _compressableType(mediaType)
                else _StyleResource
                )
            self.putChild(fileName.encode(), resourceFactory(data, mediaType))
        return data

    def addIcon(self, name: str) -> Image:
        icon = self.__icons.get(name)
        if icon is None:
            icon = self.__addIcon(name)
            self.__icons[name] = icon
        return icon

    def __addIcon(self, name: str) -> Image:
        fileName = name + '.svg'
        if importlib_resources.is_resource(styles, fileName):
            data = self.__addFile(fileName, 'image/svg+xml')
            if data is not None:
                return svgIcon(fileName, data)

        fileName = name + '.png'
        data = self.__addFile(fileName, 'image/png')
        return pngIcon(fileName, data)

    def addShortcutIcon(self, name: str) -> ShortcutIcon:
        icon = ShortcutIcon(name)
        for fileName, mediaType in icon.iterFiles():
            self.__addFile(fileName, mediaType)
        return icon

    def addStyleSheet(self, name: str) -> StyleSheet:
        fileName = name + '.css'
        data = self.__addFile(fileName, 'text/css')
        if data is not None:
            text = data.decode('utf-8')
            index = 0
            while True:
                match = _reStyleImage.search(text, index)
                if match is None:
                    break
                imageFile = match.group(1)
                self.__addFile(imageFile, 'image/png')
                index = match.end()
        return StyleSheet(fileName, data)

styleRoot = _StyleRoot()

extraPygmentsStyles = '''
table.codehilite {
    border: none;
    background: none;
}
table.codehilite tr {
    background: none;
}
table.codehilite td {
    border: none;
    padding: 0;
    font-family: monospace;
    white-space: pre-wrap;
}
table.codehilite td.lineno {
    text-align: right;
    padding-right: 1em;
}
td.lineno a {
    color: #808080;
}
td.lineno a:hover {
    color: black;
}
'''

# Note: The "codehilite" CSS class is required by the Markdown extension
#       we use for syntax highlighting.
pygmentsFormatter = HtmlFormatter(cssclass='codehilite')
def _initPygmentsSheet() -> StyleSheet:
    """Create and register Pygments style sheet."""
    fileName = 'pygments.css'
    data = (pygmentsFormatter.get_style_defs() + extraPygmentsStyles).encode()
    styleRoot.putChild(
        fileName.encode(),
        Data(data, 'text/css')
        )
    return StyleSheet(fileName, data)
pygmentsSheet = _initPygmentsSheet()

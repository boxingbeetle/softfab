# SPDX-License-Identifier: BSD-3-Clause

from softfab.databaselib import createInternalId
from softfab.timelib import getTime, secondsPerDay
from softfab.useragent import AcceptedEncodings
from softfab.webgui import ShortcutIcon, StyleSheet, pngIcon, svgIcon
from softfab import styles

from importlib_resources import is_resource, read_binary
from twisted.web import http, resource, static

from gzip import GzipFile
from io import BytesIO
import logging
import re

def _load(fileName):
    try:
        return read_binary(styles, fileName)
    except IOError as ex:
        logging.error('Error reading style resource "%s": %s', fileName, ex)
        return None

class _StyleResource(static.Data):

    def render(self, request):
        # File expires a long time from now.
        # RFC-2616 section 14.21: "HTTP/1.1 servers SHOULD NOT send Expires
        # dates more than one year in the future."
        request.setHeader(
            'expires',
            http.datetimeToString(getTime() + 365 * secondsPerDay)
            )
        return static.Data.render(self, request)

class _CompressedStyleResource(_StyleResource):

    def __init__(self, data, mediaType):
        _StyleResource.__init__(self, data, mediaType)

        # Note: Because we only compress these resources once, we might as well
        #       do it with maximum compression.
        with BytesIO() as buf:
            with GzipFile(None, 'wb', 9, buf) as zfile:
                zfile.write(data)
            gzippedData = buf.getvalue()

        self.__gzippedResource = _StyleResource(gzippedData, mediaType)

    def render(self, request):
        # Pick an encoding based on client and server preferences.
        # We strongly prefer gzip because we save on bandwidth and
        # have pre-compressed the resource.
        accept = AcceptedEncodings.parse(request.getHeader('accept-encoding'))
        if 4.0 * accept['gzip'] > accept['identity']:
            request.setHeader('Content-Encoding', 'gzip')
            return self.__gzippedResource.render(request)
        else:
            return static.Data.render(self, request)

_reStyleImage = re.compile(r'url\((\w+\.png)\)')

def _compressableType(mediaType):
    '''Returns True iff the given media type is suitable for compression.
    Compressing data twice only slows things down, so already compressed
    formats like PNG should not be compressed again, while text formats
    like CSS and XML should be compressed.
    '''
    return mediaType.startswith('text/') or mediaType.endswith('+xml')

class _StyleRoot(resource.Resource):
    # Create a new URL every time the Control Center is restarted.
    # This allows to set the expiry time really high without running the risk
    # of using outdated cached style files.
    urlPrefix = 'styles-'
    relativeURL = urlPrefix + createInternalId()

    def __init__(self):
        resource.Resource.__init__(self)
        self.__icons = {}

    def __addFile(self, fileName, mediaType):
        data = _load(fileName)
        if data is not None:
            resourceFactory = (
                _CompressedStyleResource
                if _compressableType(mediaType)
                else _StyleResource
                )
            self.putChild(fileName.encode(), resourceFactory(data, mediaType))
        return data

    def addIcon(self, name):
        icon = self.__icons.get(name)
        if icon is None:
            icon = self.__addIcon(name)
            self.__icons[name] = icon
        return icon

    def __addIcon(self, name):
        fileName = name + '.svg'
        if is_resource(styles, fileName):
            data = self.__addFile(fileName, 'image/svg+xml')
            if data is not None:
                return svgIcon(self.relativeURL + '/' + fileName, data)

        fileName = name + '.png'
        data = self.__addFile(fileName, 'image/png')
        return pngIcon(self.relativeURL + '/' + fileName, data)

    def addShortcutIcon(self, name):
        icon = ShortcutIcon(name, self.relativeURL)
        for fileName, mediaType in icon.iterFiles():
            self.__addFile(fileName, mediaType)
        return icon

    def addStyleSheet(self, name):
        fileName = name + '.css'
        data = self.__addFile(fileName, 'text/css')
        text = data.decode('utf-8')
        index = 0
        while True:
            match = _reStyleImage.search(text, index)
            if match is None:
                break
            imageFile = match.group(1)
            self.__addFile(imageFile, 'image/png')
            index = match.end()
        return StyleSheet(self.relativeURL + '/' + fileName)

styleRoot = _StyleRoot()

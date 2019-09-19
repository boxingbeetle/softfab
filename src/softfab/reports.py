# SPDX-License-Identifier: BSD-3-Clause

from codecs import getreader
from typing import Callable, IO, Optional

from pygments import highlight
from pygments.lexer import Lexer
from pygments.lexers import guess_lexer_for_filename
from pygments.util import ClassNotFound
from twisted.web.http import Request as TwistedRequest
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
import attr

from softfab.StyleResources import pygmentsFormatter, pygmentsSheet, styleRoot


@attr.s(auto_attribs=True)
class TextResource(Resource):
    """Presents a text artifact in a user friendly way.
    """
    isLeaf = True

    text: str
    fileName: str
    lexer: Lexer

    def render_GET(self, request: TwistedRequest) -> bytes:
        depth = len(request.prepath) - 1
        styleURL = '../' * depth + styleRoot.relativeURL
        styleLink = pygmentsSheet.present(styleURL=styleURL)
        request.write(
            '<!DOCTYPE html>\n'
            '<html>\n'
            '<head>\n'
            f'<title>Report: {self.fileName}</title>\n'
            f'{styleLink.flattenWithoutNamespace()}\n'
            '</head>\n'
            '<body>\n'.encode()
            )
        output = highlight(self.text, self.lexer, pygmentsFormatter)
        request.write(output.encode())
        request.write(
            '</body>\n'
            '</html>\n'.encode()
            )
        request.finish()
        return NOT_DONE_YET

UTF8Reader = getreader('utf-8')

def createPresenter(opener: Callable[[], IO[bytes]],
                    fileName: str
                    ) -> Optional[Resource]:
    """Attempt to create a custom presenter for the given artifact.
    Return a resource that handles the presentation, or None if no custom
    presentation is available or desired for this artifact.
    """

    # TODO: Perform file type detection to see if we want to do custom
    #       presentation.
    #       We can probably combine mimetypes.guess_type with the info
    #       from Pygments into a new detection function that's also used
    #       by the 'artifacts' module.
    #       Do not use source highlighting for formats that the browser
    #       can handle in non-source form, like HTML and SVG.
    if not fileName.endswith('.xml'):
        return None

    # Load file contents into a string.
    # TODO: Only do this if the file name suggests we will be able to
    #       present the contents.
    with opener() as stream:
        with UTF8Reader(stream, errors='replace') as reader:
            text = reader.read()

    try:
        lexer = guess_lexer_for_filename(fileName, text)
    except ClassNotFound:
        return None
    else:
        return TextResource(text, fileName, lexer)

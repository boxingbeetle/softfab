# SPDX-License-Identifier: BSD-3-Clause

class _FormatMeta(type):

    def __call__(cls, ext):
        try:
            return getattr(cls, ext)
        except AttributeError:
            raise ValueError('No format named "%s"' % ext)

class Format(metaclass=_FormatMeta):
    @classmethod
    def add(cls, ext, description, mediaType):
        # Bypass the metaclass __call__().
        instance = type.__call__(cls, ext, description, mediaType)
        setattr(cls, ext, instance)

    def __init__(self, ext, description, mediaType):
        self.ext = ext
        self.description = description
        self.mediaType = mediaType

    def __str__(self):
        return self.ext

Format.add('png', 'PNG image', 'image/png')
Format.add('svg', 'SVG image', 'image/svg+xml; charset=UTF-8')
Format.add('dot', 'GraphViz dot file', 'application/x-graphviz; charset=UTF-8')

def iterGraphFormats():
    '''Iterates through the available graph output formats.
    Each element is a Format instance.
    '''
    yield Format.png
    yield Format.svg
    yield Format.dot

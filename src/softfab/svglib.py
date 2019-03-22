# SPDX-License-Identifier: BSD-3-Clause

'''Presents SVG images.
'''

from typing import Optional, cast
from xml.etree import ElementTree

from softfab.webgui import Widget
from softfab.xmlgen import XMLContent, adaptToXML, xhtml

svgNamespace = 'http://www.w3.org/2000/svg'
xlinkNamespace = 'http://www.w3.org/1999/xlink'

# Register namespaces with the ElementTree module.
# This is not strictly necessary, but without this ElementTree will generate
# synthetic names like "ns0", which makes the XML output harder to read.
ElementTree.register_namespace('svg', svgNamespace)
ElementTree.register_namespace('xlink', xlinkNamespace)

svgNSPrefix = '{%s}' % svgNamespace
xlinkNSPrefix = '{%s}' % xlinkNamespace

class SVGPanel(Widget):
    '''Presents an SVG image on a panel, with the same frame and background as
    tables.
    The image should be an ElementTree passed to the present method as
    "svgElement", or it can be None, in which case the panel is not presented.
    '''

    def present(self, **kwargs: object) -> XMLContent:
        svg = cast(Optional[ElementTree.Element], kwargs.get('svgElement'))
        if svg is None:
            return None
        else:
            return xhtml.div(class_ = 'graph')[
                xhtml.div[ adaptToXML(svg) ],
                self.presentFooter(**kwargs)
                ]

    def presentFooter(self, # pylint: disable=unused-argument
                      **kwargs: object
                      ) -> XMLContent:
        '''Can be overridden to add a footer to the SVG panel.
        The default implementation does not show a footer.
        The footer should be an `xhtml.div`.
        '''
        return None

# SPDX-License-Identifier: BSD-3-Clause

import unittest

from softfab.xmlgen import xhtml

"""Test XML generation module."""

class TestScript(unittest.TestCase):
    """Test text inside the <script> XHTML element."""

    def testNoEscape(self):
        """Check that no escaping is performed when it is not necessary."""

        text = 'if (a > b) return c[3];'
        self.assertEqual(
            xhtml.script[text].flattenXML(),
            '<script xmlns="http://www.w3.org/1999/xhtml">%s</script>' % text
            )

    def testCDATA(self):
        """Check that a CDATA block is used when necessary."""

        text = 'if (a < b) return c[3];'
        self.assertEqual(
            xhtml.script[text].flattenXML(),
            '<script xmlns="http://www.w3.org/1999/xhtml">'
            '/*<![CDATA[*/%s/*]]>*/'
            '</script>'
            % text
            )

        text = 'if (a = b) return c & 3;'
        self.assertEqual(
            xhtml.script[text].flattenXML(),
            '<script xmlns="http://www.w3.org/1999/xhtml">'
            '/*<![CDATA[*/%s/*]]>*/'
            '</script>'
            % text
            )

    def testCDATAEnd(self):
        """Check that a CDATA block is not closed too early."""

        text = 'var f = x[y[i]]>0 && z<0;'
        #                    ^^^-- CDATA end marker
        self.assertEqual(
            xhtml.script[text].flattenXML(),
            '<script xmlns="http://www.w3.org/1999/xhtml">'
            '/*<![CDATA[*/var f = x[y[i]]\\>0 && z<0;/*]]>*/'
            '</script>'
            )

    def testTagEnd(self):
        """Check that a <script> tag is not closed too early."""

        text = 'var s = "</script>";'
        self.assertEqual(
            xhtml.script[text].flattenXML(),
            '<script xmlns="http://www.w3.org/1999/xhtml">'
            '/*<![CDATA[*/var s = "<\\/script>";/*]]>*/'
            '</script>'
            )

class TestStyle(unittest.TestCase):
    """Test text inside the <style> XHTML element.
    Since <script> is handled in the same way, we test fewer scenarios here.
    """

    def testNoEscape(self):
        """Check that no escaping is performed when it is not necessary."""

        text = '.nav > a[href] { color: #FFC000 }'
        self.assertEqual(
            xhtml.style[text].flattenXML(),
            '<style xmlns="http://www.w3.org/1999/xhtml">%s</style>' % text
            )

    def testCDATA(self):
        """Check that a CDATA block is used when necessary."""

        text = 'book.c /* K&R */'
        self.assertEqual(
            xhtml.style[text].flattenXML(),
            '<style xmlns="http://www.w3.org/1999/xhtml">'
            '/*<![CDATA[*/%s/*]]>*/'
            '</style>'
            % text
            )

    def testTagEnd(self):
        """Check that a <style> tag is not closed too early."""

        text = '@import url(more.css); /* </StyLe */'
        # HTML tags are case-insensitive:   ^^^^^
        self.assertEqual(
            xhtml.style[text].flattenXML(),
            '<style xmlns="http://www.w3.org/1999/xhtml">'
            '/*<![CDATA[*/@import url(more.css); /* <\\/StyLe *//*]]>*/'
            '</style>'
            )

if __name__ == '__main__':
    unittest.main()

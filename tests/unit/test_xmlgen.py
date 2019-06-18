# SPDX-License-Identifier: BSD-3-Clause

import unittest

from softfab.xmlgen import parseHTML, xhtml

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

class TestHTMLParser(unittest.TestCase):
    """Test parsing of HTML fragments."""

    def testBasic(self):
        """Check whether basic functionality works."""
        parsed = parseHTML('<h1>Hello!</h1>')
        self.assertEqual(
            parsed.flattenXML(),
            '<h1 xmlns="http://www.w3.org/1999/xhtml">Hello!</h1>'
            )

    def testMultiTopLevel(self):
        """Check whether we can handle multiple top-level tags."""
        parsed = parseHTML('<h1>Hello!</h1><h1>Goodbye!</h1>')
        self.assertEqual(
            parsed.flattenXML(),
            '<h1 xmlns="http://www.w3.org/1999/xhtml">Hello!</h1>'
            '<h1 xmlns="http://www.w3.org/1999/xhtml">Goodbye!</h1>'
            )

    def testNested(self):
        """Check handling of nested content."""
        parsed = parseHTML('<p>Text with <i>nested</i> tags.</p>')
        self.assertEqual(
            parsed.flattenXML(),
            '<p xmlns="http://www.w3.org/1999/xhtml">'
            'Text with <i>nested</i> tags.'
            '</p>'
            )

    def testVoid(self):
        """Check handling of void elements."""
        parsed = parseHTML('<p>Text with<br/>a void element.</p>')
        self.assertEqual(
            parsed.flattenXML(),
            '<p xmlns="http://www.w3.org/1999/xhtml">'
            'Text with<br/>a void element.'
            '</p>'
            )

    def testIgnorePI(self):
        """Check parsing of processing instruction with no handlers."""
        parsed = parseHTML('<p>A processing <?jump> instruction.</p>')
        self.assertEqual(
            parsed.flattenXML(),
            '<p xmlns="http://www.w3.org/1999/xhtml">'
            'A processing  instruction.'
            '</p>'
            )

    def testUnknownPI(self):
        """Check parsing of unknown processing instruction."""
        with self.assertRaises(KeyError):
            parsed = parseHTML(
                '<p>A processing <?jump> instruction.</p>',
                piHandlers={}
                )

    def testNoArgPI(self):
        """Check parsing of processing instruction with no arguments."""
        def jumpHandler(arg):
            assert arg == '', arg
            return xhtml.br
        parsed = parseHTML(
            '<p>A processing <?jump> instruction.</p>',
            piHandlers=dict(jump=jumpHandler)
            )
        self.assertEqual(
            parsed.flattenXML(),
            '<p xmlns="http://www.w3.org/1999/xhtml">'
            'A processing <br/> instruction.'
            '</p>'
            )

    def testArgPI(self):
        """Check parsing of processing instruction with an argument."""
        parsed = parseHTML(
            '<p>A processing <?jump a little higher> instruction.</p>',
            piHandlers=dict(jump=lambda arg: xhtml.span[arg])
            )
        self.assertEqual(
            parsed.flattenXML(),
            '<p xmlns="http://www.w3.org/1999/xhtml">'
            'A processing <span>a little higher</span> instruction.'
            '</p>'
            )

    def testIgnoreXMLDecl(self):
        """Check parsing of XML declaration."""
        parsed = parseHTML(
            '<?xml version="1.0" encoding="UTF-8" ?>'
            '<html><body><p>XHTML document.</p></body></html>',
            piHandlers={}
            )
        self.assertEqual(
            parsed.flattenXML(),
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            '<body><p>XHTML document.</p></body>'
            '</html>'
            )

    def testIgnoreXMLSyntax(self):
        """Check parsing of a PI using XML syntax (question mark at end)."""
        def jumpHandler(arg):
            return arg.upper()
        parsed = parseHTML(
            '<p>A processing <?jump lazy fox?> instruction.</p>',
            piHandlers=dict(jump=jumpHandler)
            )
        self.assertEqual(
            parsed.flattenXML(),
            '<p xmlns="http://www.w3.org/1999/xhtml">'
            'A processing LAZY FOX instruction.'
            '</p>'
            )

if __name__ == '__main__':
    unittest.main()

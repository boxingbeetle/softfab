# SPDX-License-Identifier: BSD-3-Clause

"""Test XML generation module."""

from pytest import raises

from softfab.xmlgen import parseHTML, xhtml


# Test text inside the <script> XHTML element:

def testScriptNoEscape():
    """Check that no escaping is performed when it is not necessary."""

    text = 'if (a > b) return c[3];'
    assert xhtml.script[text].flattenXML() == (
        f'<script xmlns="http://www.w3.org/1999/xhtml">{text}</script>'
        )

def testScriptCDATA():
    """Check that a CDATA block is used when necessary."""

    text = 'if (a < b) return c[3];'
    assert xhtml.script[text].flattenXML() == (
        f'<script xmlns="http://www.w3.org/1999/xhtml">'
        f'/*<![CDATA[*/{text}/*]]>*/'
        f'</script>'
        )

    text = 'if (a = b) return c & 3;'
    assert xhtml.script[text].flattenXML() == (
        f'<script xmlns="http://www.w3.org/1999/xhtml">'
        f'/*<![CDATA[*/{text}/*]]>*/'
        f'</script>'
        )

def testScriptCDATAEnd():
    """Check that a CDATA block is not closed too early."""

    text = 'var f = x[y[i]]>0 && z<0;'
    #                    ^^^-- CDATA end marker
    assert xhtml.script[text].flattenXML() == (
        '<script xmlns="http://www.w3.org/1999/xhtml">'
        '/*<![CDATA[*/var f = x[y[i]]\\>0 && z<0;/*]]>*/'
        '</script>'
        )

def testScriptTagEnd():
    """Check that a <script> tag is not closed too early."""

    text = 'var s = "</script>";'
    assert xhtml.script[text].flattenXML() == (
        '<script xmlns="http://www.w3.org/1999/xhtml">'
        '/*<![CDATA[*/var s = "<\\/script>";/*]]>*/'
        '</script>'
        )


# Test text inside the <style> XHTML element.
# Since <script> is handled in the same way, we test fewer scenarios here.

def testStyleNoEscape():
    """Check that no escaping is performed when it is not necessary."""

    text = '.nav > a[href] { color: #FFC000 }'
    assert xhtml.style[text].flattenXML() == (
        f'<style xmlns="http://www.w3.org/1999/xhtml">{text}</style>'
        )

def testStyleCDATA():
    """Check that a CDATA block is used when necessary."""

    text = 'book.c /* K&R */'
    assert xhtml.style[text].flattenXML() == (
        f'<style xmlns="http://www.w3.org/1999/xhtml">'
        f'/*<![CDATA[*/{text}/*]]>*/'
        f'</style>'
        )

def testStyleTagEnd():
    """Check that a <style> tag is not closed too early."""

    text = '@import url(more.css); /* </StyLe */'
    # HTML tags are case-insensitive:   ^^^^^
    assert xhtml.style[text].flattenXML() == (
        '<style xmlns="http://www.w3.org/1999/xhtml">'
        '/*<![CDATA[*/@import url(more.css); /* <\\/StyLe *//*]]>*/'
        '</style>'
        )


# Test parsing of HTML fragments:

def testBasic():
    """Check whether basic functionality works."""
    parsed = parseHTML('<h1>Hello!</h1>')
    assert parsed.flattenXML() == (
        '<h1 xmlns="http://www.w3.org/1999/xhtml">Hello!</h1>'
        )

def testMultiTopLevel():
    """Check whether we can handle multiple top-level tags."""
    parsed = parseHTML('<h1>Hello!</h1><h1>Goodbye!</h1>')
    assert parsed.flattenXML() == (
        '<h1 xmlns="http://www.w3.org/1999/xhtml">Hello!</h1>'
        '<h1 xmlns="http://www.w3.org/1999/xhtml">Goodbye!</h1>'
        )

def testNested():
    """Check handling of nested content."""
    parsed = parseHTML('<p>Text with <i>nested</i> tags.</p>')
    assert parsed.flattenXML() == (
        '<p xmlns="http://www.w3.org/1999/xhtml">'
        'Text with <i>nested</i> tags.'
        '</p>'
        )

def testVoid():
    """Check handling of void elements."""
    parsed = parseHTML('<p>Text with<br/>a void element.</p>')
    assert parsed.flattenXML() == (
        '<p xmlns="http://www.w3.org/1999/xhtml">'
        'Text with<br/>a void element.'
        '</p>'
        )

def testIgnorePI():
    """Check parsing of processing instruction with no handlers."""
    parsed = parseHTML('<p>A processing <?jump> instruction.</p>')
    assert parsed.flattenXML() == (
        '<p xmlns="http://www.w3.org/1999/xhtml">'
        'A processing  instruction.'
        '</p>'
        )

def testRaisePI():
    """Check propagation of handler exceptions."""
    def handler(name, arg):
        raise KeyError(f'unknown PI: {name}')
    with raises(KeyError):
        parseHTML(
            '<p>A processing <?jump> instruction.</p>',
            piHandler=handler
            )

def testNoArgPI():
    """Check parsing of processing instruction with no arguments."""
    def handler(name, arg):
        assert name == 'jump'
        assert arg == ''
        return xhtml.br
    parsed = parseHTML(
        '<p>A processing <?jump> instruction.</p>',
        piHandler=handler
        )
    assert parsed.flattenXML() == (
        '<p xmlns="http://www.w3.org/1999/xhtml">'
        'A processing <br/> instruction.'
        '</p>'
        )

def testArgPI():
    """Check parsing of processing instruction with an argument."""
    def handler(name, arg):
        assert name == 'jump'
        return xhtml.span[arg]
    parsed = parseHTML(
        '<p>A processing <?jump a little higher> instruction.</p>',
        piHandler=handler
        )
    assert parsed.flattenXML() == (
        '<p xmlns="http://www.w3.org/1999/xhtml">'
        'A processing <span>a little higher</span> instruction.'
        '</p>'
        )

def testIgnoreXMLDecl():
    """Check parsing of XML declaration."""
    def handler(name, arg):
        assert False
    parsed = parseHTML(
        '<?xml version="1.0" encoding="UTF-8" ?>'
        '<html><body><p>XHTML document.</p></body></html>',
        piHandler=handler
        )
    assert parsed.flattenXML() == (
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        '<body><p>XHTML document.</p></body>'
        '</html>'
        )

def testIgnoreXMLSyntax():
    """Check parsing of a PI using XML syntax (question mark at end)."""
    def handler(name, arg):
        assert name == 'jump'
        return arg.upper()
    parsed = parseHTML(
        '<p>A processing <?jump lazy fox?> instruction.</p>',
        piHandler=handler
        )
    assert parsed.flattenXML() == (
        '<p xmlns="http://www.w3.org/1999/xhtml">'
        'A processing LAZY FOX instruction.'
        '</p>'
        )

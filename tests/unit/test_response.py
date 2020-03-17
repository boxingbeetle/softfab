# SPDX-License-Identifier: BSD-3-Clause

from functools import partial

from softfab.response import _encodeHeaderValue

def test_encodeHeaderValue():
    enc = partial(_encodeHeaderValue, b'filename')
    assert enc('plain.txt') == b'filename="plain.txt"'
    assert enc('ASCII, but non-trivial!') == b'filename="ASCII, but non-trivial!"'
    assert enc('control\n') == b'''filename="control_"; filename*=UTF-8''control%0A'''
    assert enc('\u20AC.svg') == b'''filename="_.svg"; filename*=UTF-8''%E2%82%AC.svg'''

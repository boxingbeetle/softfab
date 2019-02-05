# SPDX-License-Identifier: BSD-3-Clause

from os import SEEK_CUR
from typing import IO, Tuple

_pngSignature = b'\x89PNG\r\n\x1a\n'

def _readBytes(inp: IO[bytes], length: int) -> bytes:
    value = inp.read(length)
    if len(value) == length:
        return value
    else:
        raise ValueError('Read past EOF')

def _readUInt32(inp: IO[bytes]) -> int:
    value = 0
    for byte in _readBytes(inp, 4):
        value <<= 8
        value |= byte
    return value

def getPNGDimensions(inp: IO[bytes]) -> Tuple[int, int]:
    '''Examines a PNG stream and returns the dimensions (x, y) of the image.
    If there is an error reading the file, IOError is raised.
    If there is an error decoding the PNG data, ValueError is raised.
    '''
    # Check signature.
    signature = _readBytes(inp, len(_pngSignature))
    if signature != _pngSignature:
        raise ValueError('Signature mismatch')
    # Read chunks.
    while True:
        length = _readUInt32(inp)
        typeStr = _readBytes(inp, 4)
        if typeStr == b'IHDR':
            # Image header; extract the dimensions.
            width = _readUInt32(inp)
            height = _readUInt32(inp)
            return width, height
        elif typeStr == b'IEND':
            # End of data stream.
            raise ValueError('No image header found')
        else:
            # Uninteresting chunk; skip to next.
            inp.seek(length + 4, SEEK_CUR)

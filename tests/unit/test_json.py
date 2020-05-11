# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum, auto

import attr

from softfab.json import dataToJSON


class Color(Enum):
    RED = auto()
    GREEN = auto()
    BLUE = auto()

@attr.s(auto_attribs=True)
class HeroData:
    name: str
    age: int
    knighted: bool
    fav_color: Color

knight = HeroData(name='Launcelot', age=35, knighted=True,
                  fav_color=Color.BLUE)
knightJSON = dict(name='Launcelot', age=35, knighted=True, fav_color='blue')

def testHeroDataToJSON():
    """Test whether a we can create JSON from a simple object."""
    assert dataToJSON(knight) == knightJSON

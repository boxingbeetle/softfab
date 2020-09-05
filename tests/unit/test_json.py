# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum, auto

import attr
from pytest import mark, raises

from softfab.json import dataToJSON, jsonToData, mapJSON


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

@attr.s(auto_attribs=True)
class HeroDataDefault(HeroData):
    armor: str = 'plate'
    shield: bool = True

knight = HeroData(name='Launcelot', age=35, knighted=True, fav_color=Color.BLUE)
knightJSON = dict(name='Launcelot', age=35, knighted=True, fav_color='blue')

def testHeroDataToJSON():
    """Test whether a we can create JSON from a simple object."""
    assert dataToJSON(knight) == knightJSON

def testJSONToHeroData():
    """Test whether a we can create a simple object from JSON."""
    assert jsonToData(knightJSON, HeroData) == knight

@mark.parametrize('func', [jsonToData, mapJSON])
def testBadJSON(func):
    """Test the various ways in which JSON binding can fail."""

    with raises(ValueError, match="Expected object, got array"):
        func([], HeroData)

    with raises(ValueError, match="Field 'quest' does not exist"):
        func({'quest': 'Holy Grail'}, HeroData)

    with raises(ValueError, match="Expected integer value for field 'age'"):
        func(dict(knightJSON, age='unknown'), HeroData)

    with raises(ValueError, match="Expected string value for field 'fav_color'"):
        func(dict(knightJSON, fav_color=None), HeroData)

    with raises(ValueError, match="Invalid value 'yellow' for field 'fav_color'; "
                                  "expected one of: red, green, blue"):
        func(dict(knightJSON, fav_color='yellow'), HeroData)

@mark.parametrize('obj', [{}, {'age': 35}])
def testMissingJSONFields(obj):
    """Test handling of missing fields."""

    with raises(ValueError, match="Missing values for fields:"):
        jsonToData(obj, HeroData)

    with raises(ValueError, match="Missing values for fields:"):
        mapJSON(obj, HeroData, partial=False)

    assert mapJSON(obj, HeroData, partial=True) == obj

def testJSONDefault():
    """Test binding to a data transfer class with defaults for some fields."""

    defaultKnight = jsonToData(dict(knightJSON, armor='ring'), HeroDataDefault)
    assert defaultKnight.armor == 'ring' # overridden
    assert defaultKnight.shield is True # default

def testBadDataClass():
    """Test handling of errors in the passed data class."""

    BrokenData = attr.make_class('BrokenData', ['emblem'])
    with raises(TypeError, match="No type specified for attribute 'emblem'"):
        jsonToData({'emblem': 'chicken'}, BrokenData)

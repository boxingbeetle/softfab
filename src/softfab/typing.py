# SPDX-License-Identifier: BSD-3-Clause

from typing import TYPE_CHECKING

# Make sure we only require 'typing_extensions' module during type checking.
if TYPE_CHECKING:
    from typing_extensions import Protocol
else:
    Protocol = object

# Collection was introduced in Python 3.6.
try:
    from typing import Collection
except ImportError:
    # Collection is a combination of Sized, Iterable and Container.
    # Pick Iterable since it leads to the least false positives.
    from typing import Iterable as Collection # type: ignore

# NoReturn was introduced in Python 3.6.5.
if TYPE_CHECKING:
    from typing_extensions import NoReturn
else:
    NoReturn = None

__all__ = ['Collection', 'NoReturn', 'Protocol']

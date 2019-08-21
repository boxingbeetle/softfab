# SPDX-License-Identifier: BSD-3-Clause

from typing import TYPE_CHECKING

# Make sure we only require 'typing_extensions' module during type checking.
if TYPE_CHECKING:
    from typing_extensions import Protocol
else:
    Protocol = object

# NoReturn was introduced in Python 3.6.5.
if TYPE_CHECKING:
    from typing_extensions import NoReturn
else:
    NoReturn = None


# On Python 3.7+, use importlib.resources from the standard library.
# On older versions, a compatibility package can be installed from PyPI.
try:
    import importlib.resources as importlib_resources
except ImportError:
    import importlib_resources # type: ignore


__all__ = ['NoReturn', 'Protocol', 'importlib_resources']

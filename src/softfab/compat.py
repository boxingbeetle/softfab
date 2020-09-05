# SPDX-License-Identifier: BSD-3-Clause

from typing import TYPE_CHECKING

# On Python 3.8+, use importlib.metadata from the standard library.
# On older versions, a compatibility package can be installed from PyPI.
try:
    if not TYPE_CHECKING:
        import importlib.metadata as importlib_metadata
except ImportError:
    import importlib_metadata

# On Python 3.7+, use importlib.resources from the standard library.
# On older versions, a compatibility package can be installed from PyPI.
try:
    if not TYPE_CHECKING:
        import importlib.resources as importlib_resources
except ImportError:
    import importlib_resources


__all__ = [
    'importlib_metadata', 'importlib_resources'
    ]

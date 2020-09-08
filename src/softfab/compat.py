# SPDX-License-Identifier: BSD-3-Clause

from typing import TYPE_CHECKING, List, Optional, Tuple, Type

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

# The typing_extensions package does not offer get_origin() and get_args()
# until Python 3.7.
_originFallback = False
if TYPE_CHECKING:
    # These were added to typeshed after mypy 0.780, so use fallback for now.
    _originFallback = True
else:
    try:
        from typing_extensions import get_args, get_origin
    except ImportError:
        _originFallback = True
if _originFallback:
    # These minimal implementations are sufficient for SoftFab, but are not
    # general replacements.
    _collectionsMap = {List: list}
    def get_origin(typ: Optional[Type]) -> Optional[Type]:
        origin = getattr(typ, '__origin__', None)
        return _collectionsMap.get(origin, origin)
    def get_args(typ: Optional[Type]) -> Tuple[Type, ...]:
        return getattr(typ, '__args__', ())


__all__ = [
    'get_args', 'get_origin', 'importlib_metadata', 'importlib_resources'
    ]

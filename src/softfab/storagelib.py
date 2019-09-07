# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import TYPE_CHECKING, Dict, Optional, Union, cast
from urllib.parse import urljoin


class StorageURLMixin:

    if TYPE_CHECKING:
        def _notify(self) -> None:
            ...

    def __init__(self) -> None:
        if TYPE_CHECKING:
            self._properties: Dict[str, Union[str, int, Enum]] = {}

    def setInternalStorage(self, path: str) -> None:
        """Use the Control Center's internal storage pool.
        """
        assert 'storage' not in self._properties
        assert 'url' not in self._properties
        self._properties['storage'] = 'sf.cc'
        self._properties['url'] = path
        self._notify()

    def getURL(self) -> Optional[str]:
        url = cast(Optional[str], self._properties.get('url'))
        if not url:
            return url # '' or None
        storageId = cast(Optional[str], self._properties.get('storage'))
        if storageId == 'sf.cc':
            return urljoin('jobs/', url)
        else:
            return None

    # TODO: Implement export in a new way.

    def getExportURL(self) -> Optional[str]:
        return None

    def hasExport(self) -> bool:
        return False

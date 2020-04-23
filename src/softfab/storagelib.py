# SPDX-License-Identifier: BSD-3-Clause

from abc import abstractmethod
from enum import Enum
from functools import partial
from gzip import open as openGzip
from pathlib import Path
from typing import IO, Callable, Dict, Optional, Union, cast
from urllib.parse import unquote_plus, urljoin
import logging

from softfab.config import dbDir

artifactsPath = Path(dbDir) / 'artifacts'

class StorageURLMixin:

    _properties: Dict[str, Union[str, int, Enum]]

    @abstractmethod
    def _notify(self) -> None: ...

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

    def reportOpener(self, fileName: str) -> Optional[Callable[[], IO[bytes]]]:
        """Return a function that opens a stream to the report with the given
        file name, or None if no report is stored under that name.
        """
        url = self.getURL()
        if url:
            path = artifactsPath
            for segment in url.split('/'):
                dirName = unquote_plus(segment)
                if dirName.startswith('.') or '/' in dirName:
                    logging.warning(
                        'Rejecting potentially unsafe artifact URL: %s', url
                        )
                    return None
                elif dirName:
                    path = path / dirName
            path = path / f'{fileName}.gz'
            if path.exists():
                return partial(openGzip, path)
        return None

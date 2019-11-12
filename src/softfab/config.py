# SPDX-License-Identifier: BSD-3-Clause

"""
Global configuration.
This module contains only those configuration parameters which are set once,
during installation. All other configuration is stored in the database,
so it can be modified through the web interface.
"""


from configparser import DEFAULTSECT, ConfigParser
from pathlib import Path
from typing import IO, Mapping, Optional
from urllib.parse import SplitResult, urlsplit, urlunsplit

# Note: These declarations must be ahead of their use in a 'global' statement
#       for the code to be accepted by Python < 3.8.0.
#       https://github.com/python/cpython/commit/de2aea0f

dbDir: str
"""Directory this factory's database is located in."""

rootURL = 'https://softfab.example.com/projname/'
"""The root URL of this factory. Must end with a slash."""

def loadConfig(file: IO[str]) -> None:
    """Load the configuration from an INI file.

    Raise OSError if the file couldn't be read.
    Raise configparser.Error if the file is not a valid INI file.
    Raise NameError if an unknown section or key exists in the file.
    Raise KeyError if a required key does not exist in the file.
    Raise ValueError if an invalid value is provided for a key.
    """

    config = ConfigParser()
    config.read_file(file)

    for name, section in config.items():
        if name == 'Server':
            _loadServer(name, section)
        elif name != DEFAULTSECT:
            raise NameError(f'Unknown section "{name}"')

def _loadServer(name: str, section: Mapping[str, str]) -> None:
    """Load the server configuration from an INI section.
    Can raise the same exceptions as loadConfig().
    """

    url: Optional[SplitResult] = None

    for key, value in section.items():
        if key == 'rooturl':
            try:
                url = urlsplit(value)
                # For parsing of port as a sanity check.
                url.port # pylint: disable=pointless-statement
            except ValueError as ex:
                raise ValueError(f'Bad root URL "{value}": {ex}') from ex
            if url.scheme not in ('http', 'https'):
                raise ValueError(
                    f'Unknown scheme "{url.scheme}" in root URL "{value}"'
                    )
            if url.query:
                raise ValueError(f'Root URL "{value}" contains query')
            if url.fragment:
                raise ValueError(f'Root URL "{value}" contains fragment')
        elif key == 'listen':
            # TODO: Move socket spec from command line to config file.
            pass
        else:
            raise NameError(f'Unknown key "{key}" in section "{name}"')

    if url is None:
        raise KeyError(f'Section "{name}" is missing key "rootURL"')
    else:
        path = url.path
        if not path.endswith('/'):
            path += '/'
        global rootURL
        rootURL = urlunsplit((url.scheme, url.netloc, path, '', ''))

def initConfig(path: Path) -> None:
    """Initialize the global configuration.

    The given path will be used to read configuration file from and
    as the database and logs directory.
    Can raise the same exceptions as loadConfig().
    """

    global dbDir
    dbDir = str(path)

    with open(path / 'softfab.ini', encoding='utf-8') as file:
        loadConfig(file)


# Settings for debugging and testing:

dbAtomicWrites = True
"""Enables the use atomic writes for updating database records.
This is safer but slower, therefore atomic writes are disabled during
unit testing. It is recommended to keep this enabled in production.
"""

logChanges = False
"""Enables database change logging.
This is useful for system testing; in production it should be disabled.
"""

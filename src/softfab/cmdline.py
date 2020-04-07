# SPDX-License-Identifier: BSD-3-Clause

"""
Command line interface.
"""


from os import getpid
from pathlib import Path
from typing import Callable, Optional, TypeVar
import sys

from click import (
    BadParameter, Context, ParamType, Parameter, command, group, option,
    version_option
)
from twisted.application import strports
from twisted.logger import globalLogBeginner, textFileLogObserver
from twisted.web.server import Session, Site

from softfab.version import VERSION


class LongSession(Session):
    sessionTimeout = 60 * 60 * 24 * 7 # one week in seconds

class ControlCenter(Site):
    sessionFactory = LongSession

    def __repr__(self) -> str:
        return 'ControlCenter'

def writePIDFile(path: Path) -> None:
    """Write our process ID to a text file.
    Raise OSError if writing the file failed.
    """
    with open(path, 'w', encoding='utf-8') as out:
        out.write(f'{getpid():d}\n')

class DirectoryParamType(ParamType):
    """Parameter type for specifying directories."""

    name = 'directory'

    def __init__(self, mustExist: bool):
        self.mustExist = mustExist

    def get_metavar(self, param: Parameter) -> str:
        return 'DIR'

    def convert(
            self,
            value: str,
            param: Optional[Parameter],
            ctx: Optional[Context]
            ) -> Path:

        path = Path(value)
        if path.is_dir():
            return path
        elif path.exists():
            raise BadParameter(f'Path is not a directory: {path}')
        elif self.mustExist:
            raise BadParameter(f'Directory does not exist: {path}')
        else:
            return path

Decorated = TypeVar('Decorated', bound=Callable)
Decorator = Callable[[Decorated], Decorated]

def dirOption(mustExist: bool) -> Decorator:
    return option(
        '-d', '--dir', 'path', type=DirectoryParamType(mustExist), default='.',
        help='Directory containing configuration, data and logging.')

# pylint: disable=import-outside-toplevel

@command()
@dirOption(False)
@option('--host', default='localhost',
        help='Host name or IP address at which the Control Center '
             'accepts connections.')
@option('--port', default=8100,
        help='TCP port at which the Control Center accepts connections.')
@option('--url',
        help='Public URL for the Control Center. '
             'Provide this when the Control Center is behind a reverse proxy.')
def init(
        path: Path,
        host: str,
        port: int,
        url: Optional[str]
        ) -> None:
    """Create a Control Center directory."""

    if url is None:
        url = f'http://{host}:{port:d}/'

    listen = f'tcp:interface={host}:port={port:d}'

    path.mkdir(mode=0o770, exist_ok=True)

    import softfab.config
    try:
        with softfab.config.openConfig(path, 'x') as file:
            # ConfigParser cannot write comments, so we manually format
            # our initial configuration file instead.
            print('[Server]', file=file)
            print(f'# The URL under which the Control Center is accessed '
                  f'by the end user.\n'
                  f'# In a reverse proxy setup, enter the public URL here.\n'
                  f'rootURL = {url}',
                  file=file)
            print(f'# Socket to listen to, in Twisted strports format.\n'
                  f'listen = {listen}',
                  file=file)
    except FileExistsError:
        print('Refusing to overwrite existing configuration file.',
              file=sys.stderr)
        sys.exit(1)
    except Exception as ex:
        print('Failed to create configuration file:', ex, file=sys.stderr)
        sys.exit(1)

    print(f'Control Center created in {path}.', file=sys.stderr)

@command()
@dirOption(True)
@option('--debug', is_flag=True,
        help='Enable debug features. Can leak data; use only in development.')
@option('--anonoper', is_flag=True,
        help='Give every visitor operator privileges, without logging in. '
             'Use only in development.')
def server(
        path: Path,
        debug: bool,
        anonoper: bool
        ) -> None:
    """Run a Control Center server."""

    # Inline import because this also starts the reactor,
    # which we don't need for every subcommand.
    from twisted.internet import reactor

    import softfab.config
    try:
        softfab.config.initConfig(path)
    except Exception as ex:
        print('Error reading configuration:', ex, file=sys.stderr)
        sys.exit(1)

    from softfab.initlog import initLogging
    initLogging(Path(softfab.config.dbDir))

    if debug:
        import logging
        import warnings
        logging.captureWarnings(True)
        warnings.simplefilter('default')

    # Set up Twisted's logging.
    observers = [textFileLogObserver(sys.stderr)]
    globalLogBeginner.beginLoggingTo(observers)

    # This must happen after logging has been initialized.
    from softfab.TwistedRoot import SoftFabRoot
    root = SoftFabRoot(anonOperator=anonoper)

    site = ControlCenter(root)
    site.secureCookie = not softfab.config.rootURL.startswith('http://')
    site.displayTracebacks = debug

    try:
        service = strports.service(softfab.config.endpointDesc, site)
    except ValueError as ex:
        print('Invalid socket specification:', ex, file=sys.stderr)
        sys.exit(1)

    try:
        service.startService()
    except Exception as ex:
        print('Failed to listen on socket:', ex, file=sys.stderr)
        sys.exit(1)
    else:
        reactor.addSystemEventTrigger('before', 'shutdown', service.stopService)

    pidfilePath = path / 'cc.pid'
    try:
        writePIDFile(pidfilePath)
    except OSError as ex:
        print(f'Failed to create PID file "{pidfilePath}": {ex}',
              file=sys.stderr)
        sys.exit(1)

    reactor.run()

    pidfilePath.unlink()

@command()
@dirOption(True)
def migrate(path: Path) -> None:
    """Migrate a Control Center database.
    This updates the data to the latest schema.
    Should be run after upgrading SoftFab, if the release notes say so.
    Will also repair inconsistent data and remove unreachable records.
    """

    # Read the config first; doubles as a sanity check of the 'path' option.
    import softfab.config
    try:
        softfab.config.initConfig(path)
    except Exception as ex:
        print('Error reading configuration:', ex, file=sys.stderr)
        sys.exit(1)

    # Avoid migrating a database that is in use.
    pidfilePath = path / 'cc.pid'
    if pidfilePath.is_file():
        print('PID file exists:', pidfilePath, file=sys.stderr)
        print('Stop the Control Center before migrating the data.',
              file=sys.stderr)
        sys.exit(1)

    # Avoid calling fsync on record rewrites.
    # Syncing on every file would make migrations of large databases take
    # forever. The upgrade procedure states that a backup should be made
    # before upgrading, so in case of abnormal termination the user can
    # restart the upgrade from the backup.
    softfab.config.dbAtomicWrites = False

    # Set conversion flags.
    from softfab.conversionflags import (
        setConversionFlags, setConversionFlagsForVersion
    )
    setConversionFlags()

    # Check whether we can convert from the database version in use before
    # the migration.
    import softfab.projectlib
    softfab.projectlib._projectDB.preload() # pylint: disable=protected-access
    versionStr = softfab.projectlib.project.dbVersion
    from softfab.utils import parseVersion
    error = None
    try:
        dbVersion = parseVersion(versionStr)
    except ValueError as ex:
        print(
            f"Failed to parse database version: {ex}\n"
            f"Migration aborted.",
            file=sys.stderr
            )
        sys.exit(1)
    if dbVersion < (2, 16, 0):
        print(
            f"Cannot convert database because its format "
            f"({versionStr}) is {error}.\n"
            f"Please upgrade to an earlier SoftFab version first.\n"
            f"See release notes for details.",
            file=sys.stderr
            )
        sys.exit(1)

    setConversionFlagsForVersion(dbVersion)

    from softfab.databases import convertAll
    convertAll()

@version_option(prog_name='SoftFab', version=VERSION,
                message='%(prog)s version %(version)s')
@group()
def main() -> None:
    """Command line interface to SoftFab."""
    pass

main.add_command(init)
main.add_command(server)
main.add_command(migrate)

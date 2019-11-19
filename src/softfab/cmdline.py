# SPDX-License-Identifier: BSD-3-Clause

"""
Command line interface.
"""


from os import getpid
from pathlib import Path
from typing import Optional
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

@command()
@option('-d', '--dir', 'path', type=DirectoryParamType(False), default='.',
        help='Directory containing configuration, data and logging.')
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
            print(f'# The URL under which the Control Center is reachable.\n'
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
@option('-d', '--dir', 'path', type=DirectoryParamType(True), default='.',
        help='Directory containing configuration, data and logging.')
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

    # This must happen after logging has been initialized.
    from softfab.TwistedRoot import SoftFabRoot

    # Set up Twisted's logging.
    observers = [textFileLogObserver(sys.stderr)]
    globalLogBeginner.beginLoggingTo(observers)

    pidfilePath = path / 'cc.pid'
    try:
        writePIDFile(pidfilePath)
    except OSError as ex:
        print(f'Failed to create PID file "{pidfilePath}": {ex}',
              file=sys.stderr)
        sys.exit(1)

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

    reactor.addSystemEventTrigger('before', 'shutdown', service.stopService)
    reactor.run()

    pidfilePath.unlink()

@version_option(prog_name='SoftFab', version=VERSION,
                message='%(prog)s version %(version)s')
@group()
def main() -> None:
    """Command line interface to SoftFab."""
    pass

main.add_command(init)
main.add_command(server)

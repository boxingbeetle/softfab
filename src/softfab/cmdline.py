# SPDX-License-Identifier: BSD-3-Clause

"""
Command line interface.
"""


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
@option('-d', '--dir', 'path', type=DirectoryParamType(True), default='.',
        help='Directory containing configuration, data and logging.')
@option('--debug', is_flag=True,
        help='Enable debug features. Can leak data; use only in development.')
@option('--no-auth', is_flag=True,
        help='Disable authentication. Use only in development.')
@option('--insecure-cookie', is_flag=True,
        help='Allow cookies to be sent over plain HTTP.')
def server(
        path: Path,
        debug: bool,
        no_auth: bool,
        insecure_cookie: bool
        ) -> None:
    """Run a SoftFab Control Center."""

    # Inline import because this also starts the reactor,
    # which we don't need for every subcommand.
    from twisted.internet import reactor

    import softfab.config
    try:
        softfab.config.initConfig(Path('.'))
    except Exception as ex:
        print('Error reading configuration:', ex, file=sys.stderr)
        sys.exit(1)

    # Importing of this module triggers the logging system initialisation.
    import softfab.initlog

    if debug:
        import logging
        import warnings
        logging.captureWarnings(True)
        warnings.simplefilter('default')

    # This must be after importing initlog.
    from softfab.TwistedRoot import SoftFabRoot

    # Set up Twisted's logging.
    observers = [textFileLogObserver(sys.stderr)]
    globalLogBeginner.beginLoggingTo(observers)

    root = SoftFabRoot(anonOperator=no_auth)

    site = Site(root)
    site.sessionFactory = LongSession
    site.secureCookie = not insecure_cookie
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

@version_option(prog_name='SoftFab', version=VERSION,
                message='%(prog)s version %(version)s')
@group()
def main() -> None:
    """Command line interface to SoftFab."""
    pass

main.add_command(server)

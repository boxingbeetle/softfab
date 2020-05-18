# SPDX-License-Identifier: BSD-3-Clause

"""
Command line interface.
"""


from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Optional, TypeVar
import sys

from click import (
    BadParameter, Choice, Context, ParamType, Parameter, argument, echo,
    get_current_context, group, option, pass_context, pass_obj, version_option,
    wrap_text
)

from softfab.roles import UIRoleNames

if TYPE_CHECKING:
    from twisted.web.iweb import IAgentEndpointFactory


# We import inside functions to avoid wasting time importing modules that the
# issued command doesn't need. Another reason is to avoid side effects from
# loading modules, but that is an issue we want to eliminate at some point.
# pylint: disable=import-outside-toplevel

class DirectoryParamType(ParamType):
    """Parameter type for specifying directories."""

    name = 'directory'

    def get_metavar(self, param: Parameter) -> str:
        return 'DIR'

    def convert(
            self,
            value: str,
            param: Optional[Parameter],
            ctx: Optional[Context]
            ) -> Path:

        path = Path(value)
        if path.exists() and not path.is_dir():
            raise BadParameter(f'Path is not a directory: {path}')
        else:
            return path

class OutputFormat(Enum):
    TEXT = auto()
    JSON = auto()

class GlobalOptions:

    def __init__(self, debug: bool, path: Path):
        self.debug = debug
        self.path = path

    @property
    def endpointFactory(self) -> 'IAgentEndpointFactory':
        from softfab.site import ControlSocketFactory

        return ControlSocketFactory(self.path)

    def apply(self) -> None:
        """Initialize Control Center configuration according to
        the global options.
        """

        path = self.path
        if not path.is_dir():
            echo(f"Path is not a directory: {path}", err=True)
            get_current_context().exit(1)

        # Read the config first.
        # This doubles as a sanity check of the 'path' option.
        import softfab.config
        try:
            softfab.config.initConfig(path)
        except Exception as ex:
            echo(f"Error reading configuration: {ex}", err=True)
            get_current_context().exit(1)

        from softfab.initlog import initLogging
        initLogging(path)

        if self.debug:
            import logging
            import warnings
            logging.captureWarnings(True)
            warnings.simplefilter('default')

    def urlForPath(self, path: str) -> str:
        """Return a full URL for accessing the given API path."""

        # Scheme and host are ignored since we connect through a UNIX socket,
        # but we need to include them to make a valid URL.
        return f'http://cmdline/{path}'

def formatDetails(message: str) -> str:
    """Format text explaining details for display below a main result."""
    return wrap_text(message, initial_indent='  ', subsequent_indent='  ')

T = TypeVar('T')

def callAPI(request: Awaitable[T]) -> T:
    """Make an API call and report errors to the user.
    Return the call's result.
    """

    from softfab.apiclient import runInReactor

    try:
        return runInReactor(request)
    except Exception as ex:
        message = str(ex)
        message = message[message.find('\n') + 1:]
        echo(f"softfab: {message}", err=True)
        get_current_context().exit(1)


@group()
@option('--debug', is_flag=True,
        help='Enable debug features. Can leak data; use only in development.')
@option('-d', '--dir', 'path', type=DirectoryParamType(), default='.',
        help='Directory containing configuration, data and logging.')
@version_option(prog_name='SoftFab', message='%(prog)s version %(version)s')
@pass_context
def main(ctx: Context, debug: bool, path: Path) -> None:
    """Command line interface to SoftFab."""
    ctx.obj = GlobalOptions(debug=debug, path=path)

@main.command()
@option('--host', default='localhost',
        help='Host name or IP address at which the Control Center '
             'accepts connections.')
@option('--port', default=8100,
        help='TCP port at which the Control Center accepts connections.')
@option('--url',
        help='Public URL for the Control Center. '
             'Provide this when the Control Center is behind a reverse proxy.')
@pass_obj
def init(
        globalOptions: GlobalOptions,
        host: str,
        port: int,
        url: Optional[str]
        ) -> None:
    """Create a Control Center directory."""

    if url is None:
        url = f'http://{host}:{port:d}/'

    listen = f'tcp:interface={host}:port={port:d}'

    path = globalOptions.path
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
        echo("Refusing to overwrite existing configuration file.", err=True)
        get_current_context().exit(1)
    except Exception as ex:
        echo(f"Failed to create configuration file: {ex}", err=True)
        get_current_context().exit(1)

    echo(f"Control Center created in {path}.", err=True)

@main.command()
@option('--anonoper', is_flag=True,
        help='Give every visitor operator privileges, without logging in. '
             'Use only in development.')
@pass_obj
def server(
        globalOptions: GlobalOptions,
        anonoper: bool
        ) -> None:
    """Run a Control Center server."""

    globalOptions.apply()

    # Set up Twisted's logging.
    from twisted.logger import globalLogBeginner, textFileLogObserver
    observers = [textFileLogObserver(sys.stderr)]
    globalLogBeginner.beginLoggingTo(observers)

    # This must happen after logging has been initialized.
    from softfab.TwistedRoot import SoftFabRoot
    from softfab.site import ControlCenter, ControlSocket, writePIDFile
    root = SoftFabRoot(anonOperator=anonoper)

    import softfab.config
    site = ControlCenter(root)
    site.secureCookie = not softfab.config.rootURL.startswith('http://')
    site.displayTracebacks = globalOptions.debug

    from twisted.application import strports
    try:
        service = strports.service(softfab.config.endpointDesc, site)
    except ValueError as ex:
        echo(f"Invalid socket specification: {ex}", err=True)
        get_current_context().exit(1)

    from twisted.internet import reactor
    try:
        service.startService()
    except Exception as ex:
        echo(f"Failed to listen on socket: {ex}", err=True)
        get_current_context().exit(1)
    else:
        reactor.addSystemEventTrigger('before', 'shutdown', service.stopService)

    pidfilePath = globalOptions.path / 'cc.pid'
    try:
        writePIDFile(pidfilePath)
    except OSError as ex:
        echo(f"Failed to create PID file '{pidfilePath}': {ex}", err=True)
        get_current_context().exit(1)

    from twisted.internet.interfaces import IReactorUNIX
    if IReactorUNIX.providedBy(reactor):
        from softfab.newapi import createAPIRoot
        socketPath = globalOptions.path / 'ctrl.sock'
        if socketPath.is_socket():
            # Remove stale socket.
            # TODO: Check it is actually stale.
            socketPath.unlink()
        reactor.listenUNIX(
            str(socketPath),
            ControlSocket(createAPIRoot()),
            mode=0o600
            )
    else:
        echo("Reactor does not support UNIX sockets; "
             "control socket not available", err=True)

    reactor.run()

    pidfilePath.unlink()

@main.command()
@pass_obj
def migrate(globalOptions: GlobalOptions) -> None:
    """Migrate a Control Center database.
    This updates the data to the latest schema.
    Should be run after upgrading SoftFab, if the release notes say so.
    Will also repair inconsistent data and remove unreachable records.
    """

    globalOptions.apply()

    # Avoid migrating a database that is in use.
    pidfilePath = globalOptions.path / 'cc.pid'
    if pidfilePath.is_file():
        echo(f"PID file exists: {pidfilePath}", err=True)
        echo("Stop the Control Center before migrating the data.", err=True)
        get_current_context().exit(1)

    # Avoid calling fsync on record rewrites.
    # Syncing on every file would make migrations of large databases take
    # forever. The upgrade procedure states that a backup should be made
    # before upgrading, so in case of abnormal termination the user can
    # restart the upgrade from the backup.
    import softfab.config
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
    try:
        dbVersion = parseVersion(versionStr)
    except ValueError as ex:
        echo(f"Failed to parse database version: {ex}\n"
             f"Migration aborted.", err=True)
        get_current_context().exit(1)
    if dbVersion < (2, 16, 0):
        echo(f"Cannot migrate database because its format "
             f"({versionStr}) is too old.\n"
             f"Please upgrade to an earlier SoftFab version first.\n"
             f"See release notes for details.", err=True)
        get_current_context().exit(1)

    setConversionFlagsForVersion(dbVersion)

    import logging
    from softfab.version import VERSION
    logging.info("Migrating from version %s to version %s", versionStr, VERSION)
    try:
        from softfab.databases import convertAll
        convertAll()
    except Exception as ex:
        logging.exception("Migration aborted with error: %s", ex)
        raise
    else:
        logging.info("Migration complete")

@main.group()
def user() -> None:
    """Query and modify user accounts."""

@user.command()
@argument('name')
@option('--text', 'fmt', flag_value=OutputFormat.TEXT, default=True,
        help="Output as human-readable text.")
@option('--json', 'fmt', flag_value=OutputFormat.JSON,
        help="Output as JSON.")
@pass_obj
def show(globalOptions: GlobalOptions, name: str, fmt: OutputFormat) -> None:
    """Show details of a single user account."""

    from softfab.apiclient import run_GET

    result = callAPI(run_GET(
            globalOptions.endpointFactory,
            globalOptions.urlForPath(f'users/{name}.json')
            ))
    if fmt is OutputFormat.TEXT:
        import json
        data = json.loads(result)
        for key, value in data.items():
            echo(f"{key}: {value}")
    else:
        echo(result.decode())

@user.command()
@argument('name')
@option('-r', '--role',
        type=Choice([role.name.lower()
                     for role in UIRoleNames
                     if role is not UIRoleNames.INACTIVE]),
        default='user', show_default=True,
        help="New user's role, which determines access permissions.")
@pass_obj
def add(globalOptions: GlobalOptions, name: str, role: str) -> None:
    """Create a new user account."""

    import json
    from softfab.apiclient import run_PUT

    callAPI(run_PUT(
            globalOptions.endpointFactory,
            globalOptions.urlForPath(f'users/{name}.json'),
            json.dumps(dict(name=name, role=role)).encode()
            ))
    echo(f"softfab: {role.title()} account '{name}' created", err=True)
    # TODO: Produce a password reset link.

userRemoveDoc = """
To preserve a meaningful history, we recommend to not remove user accounts
that are no longer in use, but instead set their role to 'inactive'.
If you are certain you want to remove the account completely,
use the --force flag.
""".strip().replace('\n', ' ')

@user.command(help=f"Remove a user account.\n\n{userRemoveDoc}")
@option('-f', '--force', is_flag=True, help='Force removal.')
@argument('name')
@pass_obj
def remove(globalOptions: GlobalOptions, name: str, force: bool) -> None:
    from softfab.apiclient import run_DELETE

    if not force:
        echo(f"softfab: user account was NOT removed\n\n"
             f"{formatDetails(userRemoveDoc)}", err=True)
        get_current_context().exit(2)

    callAPI(run_DELETE(
            globalOptions.endpointFactory,
            globalOptions.urlForPath(f'users/{name}')
            ))
    echo(f"softfab: user account '{name}' removed", err=True)

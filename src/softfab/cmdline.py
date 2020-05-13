# SPDX-License-Identifier: BSD-3-Clause

"""
Command line interface.
"""


from enum import Enum, auto
from os import getpid
from pathlib import Path
from typing import Awaitable, Callable, Optional, TypeVar
import json
import sys

from click import (
    BadParameter, Context, ParamType, Parameter, argument, echo,
    get_current_context, group, option, pass_context, pass_obj, version_option,
    wrap_text
)
from twisted.application import strports
from twisted.internet.endpoints import clientFromString
from twisted.internet.interfaces import IReactorUNIX, IStreamClientEndpoint
from twisted.logger import globalLogBeginner, textFileLogObserver
from twisted.web.client import URI
from twisted.web.iweb import IAgentEndpointFactory
from twisted.web.server import Session, Site
from zope.interface import implementer
import attr

from softfab.apiclient import runInReactor, run_DELETE, run_GET, run_PUT
from softfab.roles import UIRoleNames
from softfab.version import VERSION


class LongSession(Session):
    sessionTimeout = 60 * 60 * 24 * 7 # one week in seconds

class ControlCenter(Site):
    sessionFactory = LongSession

    secureCookie: bool
    """Mark session cookie as secure.
    When True, the browser will only transmit it over HTTPS.
    """

    def __repr__(self) -> str:
        return 'ControlCenter'

class ControlSocket(Site):

    def __repr__(self) -> str:
        return 'ControlSocket'

def writePIDFile(path: Path) -> None:
    """Write our process ID to a text file.
    Raise OSError if writing the file failed.
    """
    with open(path, 'w', encoding='utf-8') as out:
        out.write(f'{getpid():d}\n')

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

Decorated = TypeVar('Decorated', bound=Callable)
Decorator = Callable[[Decorated], Decorated]

class OutputFormat(Enum):
    TEXT = auto()
    JSON = auto()

# We import inside functions to avoid wasting time importing modules that the
# issued command doesn't need. Another reason is to avoid side effects from
# loading modules, but that is an issue we want to eliminate at some point.
# pylint: disable=import-outside-toplevel

@implementer(IAgentEndpointFactory)
@attr.s(auto_attribs=True)
class GlobalOptions:
    debug: bool
    path: Path

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

    def endpointForURI(self,
                       uri: URI # pylint: disable=unused-argument
                       ) -> IStreamClientEndpoint:
        """Return an endpoint for contacting the Control Center.
        Raise OSError if there is no control socket in the data directory.
        """

        from twisted.internet import reactor

        socketPath = (self.path / 'ctrl.sock').resolve()
        if socketPath.is_socket():
            return clientFromString(reactor, f'unix:{socketPath}:timeout=10')
        else:
            raise OSError(f"Control socket not found: {socketPath}")

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
@version_option(prog_name='SoftFab', version=VERSION,
                message='%(prog)s version %(version)s')
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

    # Inline import because this also starts the reactor,
    # which we don't need for every subcommand.
    from twisted.internet import reactor

    globalOptions.apply()

    # Set up Twisted's logging.
    observers = [textFileLogObserver(sys.stderr)]
    globalLogBeginner.beginLoggingTo(observers)

    # This must happen after logging has been initialized.
    from softfab.TwistedRoot import SoftFabRoot
    root = SoftFabRoot(anonOperator=anonoper)

    import softfab.config
    site = ControlCenter(root)
    site.secureCookie = not softfab.config.rootURL.startswith('http://')
    site.displayTracebacks = globalOptions.debug

    try:
        service = strports.service(softfab.config.endpointDesc, site)
    except ValueError as ex:
        echo(f"Invalid socket specification: {ex}", err=True)
        get_current_context().exit(1)

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

roleDoc = f"""
ROLE can be {', '.join(f"'{role.name.lower()}'" for role in UIRoleNames)}.
"""

@user.command()
@argument('name')
@option('--text', 'fmt', flag_value=OutputFormat.TEXT, default=True,
        help="Output as human-readable text.")
@option('--json', 'fmt', flag_value=OutputFormat.JSON,
        help="Output as JSON.")
@pass_obj
def show(globalOptions: GlobalOptions, name: str, fmt: OutputFormat) -> None:
    """Show details of a single user account."""

    result = callAPI(run_GET(
            globalOptions,
            globalOptions.urlForPath(f'users/{name}.json')
            ))
    if fmt is OutputFormat.TEXT:
        data = json.loads(result)
        for key, value in data.items():
            echo(f"{key}: {value}")
    else:
        echo(result.decode())

@user.command(help=f"Create a new user account.\n{roleDoc}")
@argument('name')
@argument('role')
@pass_obj
def add(globalOptions: GlobalOptions, name: str, role: str) -> None:
    callAPI(run_PUT(
            globalOptions,
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
    if not force:
        echo(f"softfab: user account was NOT removed\n\n"
             f"{formatDetails(userRemoveDoc)}", err=True)
        get_current_context().exit(2)

    callAPI(run_DELETE(
            globalOptions,
            globalOptions.urlForPath(f'users/{name}')
            ))
    echo(f"softfab: user account '{name}' removed", err=True)

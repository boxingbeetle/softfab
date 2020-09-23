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
    from twisted.internet.interfaces import IReactorCore
    from twisted.web.iweb import IAgent


# We import inside functions to avoid wasting time importing modules that the
# issued command doesn't need. Another reason is to avoid side effects from
# loading modules, but that is an issue we want to eliminate at some point.
# pylint: disable=import-outside-toplevel

# There is overlap between command names and argument names, such as "role".
# pylint: disable=redefined-outer-name

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
        from softfab.reactor import reactor
        self.reactor = reactor

    @property
    def agent(self) -> 'IAgent':
        from twisted.web.client import Agent
        from softfab.site import ControlSocketFactory

        # Sanity checks on data dir, to provide more useful error messages.
        path = self.path
        if not (path / 'softfab.ini').exists():
            # Currently directory is the default path.
            current = str(path) == '.'
            echo(f"No 'softfab.ini' in {'current' if current else 'given'} "
                 f"directory: {path.resolve()}", err=True)
            if current:
                echo(f"Use 'softfab --dir DIR COMMAND ...' to specify "
                     f"the data  directory.", err=True)
            get_current_context().exit(2)
        if not (path / 'ctrl.sock').exists():
            echo("No control socket in data directory; "
                 "is the Control Center running?", err=True)
            get_current_context().exit(2)

        reactor = self.reactor
        endpointFactory = ControlSocketFactory(reactor, path)
        return Agent.usingEndpointFactory(reactor, endpointFactory)

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

def callAPI(reactor: 'IReactorCore', request: Awaitable[T]) -> T:
    """Make an API call and report errors to the user.
    Return the call's result.
    """

    from softfab.apiclient import runInReactor

    try:
        return runInReactor(reactor, request)
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
    reactor = globalOptions.reactor
    root = SoftFabRoot(globalOptions.path, reactor, anonOperator=anonoper)

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
        socketPath = globalOptions.path / 'ctrl.sock'
        if socketPath.is_socket():
            # Remove stale socket.
            # TODO: Check it is actually stale.
            socketPath.unlink()
        reactor.listenUNIX(
            str(socketPath),
            ControlSocket(root.apiRoot),
            mode=0o600, backlog=50, wantPID=False
            )
    else:
        echo("Reactor does not support UNIX sockets; "
             "control socket not available", err=True)

    from softfab.TwistedUtil import runCoroutine
    reactor.callWhenRunning(runCoroutine, reactor, root.startup())
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

    from softfab.migration import migrateData
    migrateData()

def userPath(name: str) -> str:
    """The API path for accessing the given user.
    If the name is not valid as a user name, exit with an error.
    """
    from softfab.userlib import UserDB
    try:
        UserDB.checkId(name)
    except KeyError as ex:
        echo(f"softfab: {ex.args[0]}", err=True)
        get_current_context().exit(2)
    return f'users/{name}'

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

    result = callAPI(globalOptions.reactor, run_GET(
            globalOptions.agent,
            globalOptions.urlForPath(userPath(name))
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
        type=Choice([uiRole.name.lower()
                     for uiRole in UIRoleNames
                     if uiRole is not UIRoleNames.INACTIVE]),
        default='user', show_default=True,
        help="New user's role, which determines access permissions.")
@pass_obj
def add(globalOptions: GlobalOptions, name: str, role: str) -> None:
    """Create a new user account."""

    import json
    from softfab.apiclient import run_PUT

    result = callAPI(globalOptions.reactor, run_PUT(
        globalOptions.agent,
        globalOptions.urlForPath(userPath(name)),
        json.dumps(dict(role=role, password='reset')).encode()
        ))
    echo(f"softfab: {role.title()} account '{name}' created", err=True)
    presentResetURL(name, result)

userRemoveDoc = """
To preserve a meaningful history, we recommend to not remove user accounts
that are no longer in use, but block them instead.
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
        echo(f"softfab: Account was NOT removed\n\n"
             f"{formatDetails(userRemoveDoc)}", err=True)
        get_current_context().exit(2)

    callAPI(globalOptions.reactor, run_DELETE(
            globalOptions.agent,
            globalOptions.urlForPath(userPath(name))
            ))
    echo(f"softfab: Account '{name}' removed", err=True)

@user.command()
@argument('name')
@pass_obj
def block(globalOptions: GlobalOptions, name: str) -> None:
    """Block a user account.

    This sets the account's role to 'inactive' and removes the password.
    """

    updateUser(globalOptions, name, role='inactive', password='remove')
    echo(f"softfab: Account '{name}' blocked", err=True)

@user.command()
@argument('name')
@argument('role', type=Choice([uiRole.name.lower() for uiRole in UIRoleNames]))
@pass_obj
def role(globalOptions: GlobalOptions, name: str, role: str) -> None:
    """Change the role (permissions) of a user account."""

    updateUser(globalOptions, name, role=role)
    echo(f"softfab: Role of account '{name}' set to '{role}'", err=True)

@user.command()
@argument('name')
@pass_obj
def reset(globalOptions: GlobalOptions, name: str) -> None:
    """Reset the password of a user account.

    Outputs a URL at which the user can set a new password.
    """

    result = updateUser(globalOptions, name, password='reset')
    echo(f"softfab: Password of account '{name}' was reset", err=True)
    presentResetURL(name, result)

def updateUser(globalOptions: GlobalOptions,
               name: str,
               **updates: str
               ) -> bytes:
    import json
    from softfab.apiclient import run_PATCH

    return callAPI(globalOptions.reactor, run_PATCH(
        globalOptions.agent,
        globalOptions.urlForPath(userPath(name)),
        json.dumps(updates).encode()
        ))

def presentResetURL(name: str, result: bytes) -> None:
    import json
    data = json.loads(result)
    echo(f"A new password for '{name}' can be set by visiting:")
    echo(data['reset']['url'])

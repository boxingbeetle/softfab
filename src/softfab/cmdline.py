# SPDX-License-Identifier: BSD-3-Clause

"""
Command line interface.
"""


from os import getcwd
import sys

from click import command, group, option, version_option
from twisted.application import strports
from twisted.internet.error import CannotListenError
from twisted.logger import globalLogBeginner, textFileLogObserver
from twisted.web.server import Session, Site

from softfab.version import VERSION


class LongSession(Session):
    sessionTimeout = 60 * 60 * 24 * 7 # one week in seconds

@command()
@option('--listen', metavar='SOCKET',
        default='tcp:interface=localhost:port=8180',
        help='Socket to listen to, in Twisted strports format.')
@option('--debug', is_flag=True,
        help='Enable debug features. Can leak data; use only in development.')
@option('--no-auth', is_flag=True,
        help='Disable authentication. Use only in development.')
@option('--insecure-cookie', is_flag=True,
        help='Allow cookies to be sent over plain HTTP.')
def server(
        listen: str,
        debug: bool,
        no_auth: bool,
        insecure_cookie: bool
        ) -> None:
    """Run a SoftFab Control Center."""

    # Inline import because this also starts the reactor,
    # which we don't need for every subcommand.
    from twisted.internet import reactor

    import softfab.config
    softfab.config.dbDir = getcwd()

    # Importing of this module triggers the logging system initialisation.
    import softfab.initlog

    # This must be after importing initlog.
    from softfab.TwistedRoot import SoftFabRoot

    # Set up Twisted's logging.
    observers = [textFileLogObserver(sys.stderr)]
    globalLogBeginner.beginLoggingTo(observers)

    root = SoftFabRoot(debugSupport=debug, anonOperator=no_auth)

    site = Site(root)
    site.sessionFactory = LongSession
    site.secureCookie = not insecure_cookie

    try:
        service = strports.service(listen, site)
    except ValueError as ex:
        print('Invalid socket specification:', ex, file=sys.stderr)
        sys.exit(1)

    try:
        service.startService()
    except CannotListenError as ex:
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

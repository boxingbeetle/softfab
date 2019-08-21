# SPDX-License-Identifier: BSD-3-Clause

'''
Main module for starting the Control Center inside Twisted.
'''

from os import getcwd


def _createRoot(**config):
    import softfab.config
    softfab.config.dbDir = getcwd()

    # Importing of this module triggers the logging system initialisation.
    import softfab.initlog

    # This must be after importing initlog.
    from softfab.TwistedRoot import SoftFabRoot

    return SoftFabRoot(**config)

def _signalHandler(signum, frame):
    from twisted.python import log
    log.msg('Received SIGINT, stopping reactor.')
    from twisted.internet import reactor
    reactor.callFromThread(reactor.stop)

def _installSignalHandler():
    """Install our own handler for SIGINT.

    If the reactor handles the signal, 'twist' will re-raise it with
    the default signal handler set, causing the process to exit abruptly,
    which in turn means the coverage tool can't save its collected data.
    We avoid this by installing our own handler.
    """
    import signal
    signal.signal(signal.SIGINT, _signalHandler)

# The "twist" launcher will call one of these functions to create
# the root resource.
# Currently the root runs the startup process, so there must be exactly
# one root. Multiple roots might be supported in the future, since that
# would allow exposing different user and programming interfaces to
# different networks.

def production():
    """Creates a root resource for production sites.
    """
    return _createRoot(
        debugSupport=False,
        anonOperator=False,
        secureCookie=True
        )

def debug():
    """Creates a root resource for development sites.
    """
    _installSignalHandler()
    return _createRoot(
        debugSupport=True,
        anonOperator=True,
        secureCookie=False
        )

def debugAuth():
    """Creates a root resource for development sites,
    with mandatory authentication.
    """
    _installSignalHandler()
    return _createRoot(
        debugSupport=True,
        anonOperator=False,
        secureCookie=False
        )

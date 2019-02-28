# SPDX-License-Identifier: BSD-3-Clause

'''
Main module for starting the Control Center inside Twisted.
'''

from os import getcwd

def _createRoot(**config):
    import softfab.config
    softfab.config.dbDir = getcwd()

    # Importing of this module triggers the logging system initialisation.
    import softfab.initlog # pylint: disable=unused-import

    # This must be after importing initlog.
    from softfab.TwistedRoot import SoftFabRoot

    return SoftFabRoot(**config)

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
    return _createRoot(
        debugSupport=True,
        anonOperator=True,
        secureCookie=False
        )

def debugAuth():
    """Creates a root resource for development sites,
    with mandatory authentication.
    """
    return _createRoot(
        debugSupport=True,
        anonOperator=False,
        secureCookie=False
        )

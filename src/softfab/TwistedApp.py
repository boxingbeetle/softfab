# SPDX-License-Identifier: BSD-3-Clause

'''
Main module for starting the Control Center inside Twisted.
'''

# pylint: disable=ungrouped-imports,useless-suppression
# ungrouped-imports is the message we actually want to suppress,
# but because of a bug we have to disable useless-suppression too.
#   https://github.com/PyCQA/pylint/issues/2366

# Importing of this module triggers the logging system initialisation.
import softfab.initlog # pylint: disable=unused-import

# This must be after importing initlog
from softfab.TwistedRoot import SoftFabRoot

# The "twist" launcher will create an instance of one of these roots.
# Currently the root runs the startup process, so there must be exactly
# one root. Multiple roots might be supported in the future, since that
# would allow exposing different user and programming interfaces to
# different networks.

class Root(SoftFabRoot):
    """Root resource for production sites.
    """
    debugSupport = False

class DebugRoot(SoftFabRoot):
    """Root resource for development sites.
    """
    debugSupport = True

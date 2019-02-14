# SPDX-License-Identifier: BSD-3-Clause

'''
Main module for starting the Control Center inside Twisted.
'''

# pylint: disable=ungrouped-imports,useless-suppression
# ungrouped-imports is the message we actually want to suppress,
# but because of a bug we have to disable useless-suppression too.
#   https://github.com/PyCQA/pylint/issues/2366

from twisted.web import server

# Importing of this module triggers the logging system initialisation.
import softfab.initlog # pylint: disable=unused-import

# This must be after importing initlog
from softfab.TwistedRoot import SoftFabRoot

# TODO: Can we set this timeout on individual sessions instead?
server.Session.sessionTimeout = 60 * 60 * 24 * 7 # one week in seconds

# The "twist" launcher will create an instance.
Root = SoftFabRoot

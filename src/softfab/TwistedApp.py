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
import gc

# Old objects are recycled when their reference count reaches zero.
# Python can do a mark-and-sweep garbage collection as well, to clean up
# clusters of objects which are unreachable but have non-zero reference counts
# due to cyclic references. However, this mark-and-sweep blocks the Python VM
# for a while, depending on how many objects exist. For large factories, it can
# take seconds or even minutes to check everything. Therefore we decided to
# rely purely on reference counting and write code for explicitly breaking
# reference cycles.
gc.disable()

# TODO: Can we set this timeout on individual sessions instead?
server.Session.sessionTimeout = 60 * 60 * 24 * 7 # one week in seconds

# The "twist" launcher will create an instance.
Root = SoftFabRoot

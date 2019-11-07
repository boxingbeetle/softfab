# SPDX-License-Identifier: BSD-3-Clause

# Configuration of a SoftFab.
# This file contains only those configuration parameters which are set once,
# during installation. All other configuration is stored in the database,
# so it can be modified through the web interface.


# The root URL of this fab (must end with slash)
rootURL = 'https://softfab.example.com/projname/'

# Directory this fab's database is located in.
dbDir = 'run'


# Settings for debugging and testing:

loggingLevel = 'INFO'
"""Logging level.
Can be an integer or a string identifying one of the predefined
logging levels: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'.
"""

dbAtomicWrites = True
"""Enables the use atomic writes for updating database records.
This is safer but slower, therefore atomic writes are disabled during
unit testing. It is recommended to keep this enabled in production.
"""

logChanges = False
"""Enables database change logging.
This is useful for system testing; in production it should be disabled.
"""

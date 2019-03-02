# SPDX-License-Identifier: BSD-3-Clause

# Configuration of a SoftFab.
# This file contains only those configuration parameters which are set once,
# during installation. All other configuration is stored in the database,
# so it can be modified through the web interface.


# The root URL of this fab (must end with slash)
rootURL = 'https://softfab.example.com/projname/'

# The SoftFab homepage
homePage = 'https://boxingbeetle.com/tools/softfab/'

# The SoftFab documentation page
docPage = 'https://softfab.example.com/docs'

# Directory this fab's database is located in.
dbDir = 'run'

# Enables the use atomic writes for updating database records.
# This is safer but slower, therefore atomic writes are disabled during
# unit testing. It is recommended to keep this enabled in production.
dbAtomicWrites = True

# Logging level (can be an integer or a string identifying one of the
# predefined logging levels: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
loggingLevel = 'INFO'

# Delay between the syncronization requests (seconds)
syncDelay = 10

# Enables database change logging.
# This is useful for system testing; in production it should be disabled.
logChanges = False

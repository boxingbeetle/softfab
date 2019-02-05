# SPDX-License-Identifier: BSD-3-Clause

'''Collection of flags that control what kind of database conversions should
be applied. It is used during upgrade.

We used to keep these flags in the module they apply to, but that does not
work since some module initialisations load records from other databases,
causing them to be parsed before the flags are set up.
'''

import sys

# Set during any upgrade.
upgradeInProgress = False

# COMPAT 2.11: Project time zone offset.
timeOffset = 0

# COMPAT 2.12: Rename "sut" to "tr".
renameSUT = False

# COMPAT 2.13: Rename "tr" to "sf.tr".
renameTR = False

def setConversionFlags():
    '''Sets all conversion flags to True.
    '''
    variables = sys.modules[__name__].__dict__
    for name in list(variables.keys()):
        if isinstance(variables[name], bool):
            variables[name] = True

def setConversionFlagsForVersion(version):
    '''Sets conversion flags according to the given version that we are
    converting from.
    '''
    global renameSUT, renameTR
    renameSUT = version < (2, 13, 0)
    renameTR = version < (2, 14, 0)

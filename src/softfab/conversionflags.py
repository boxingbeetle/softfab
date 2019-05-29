# SPDX-License-Identifier: BSD-3-Clause

'''Collection of flags that control what kind of database conversions should
be applied. It is used during upgrade.

We used to keep these flags in the module they apply to, but that does not
work since some module initialisations load records from other databases,
causing them to be parsed before the flags are set up.
'''

from typing import Dict, Tuple
import sys

# Set during any upgrade.
upgradeInProgress = False

def setConversionFlags() -> None:
    '''Sets all conversion flags to True.
    '''
    variables = sys.modules[__name__].__dict__ # type: Dict[str, object]
    for name in list(variables.keys()):
        if isinstance(variables[name], bool):
            variables[name] = True

def setConversionFlagsForVersion(
        version: Tuple[int, int, int] # pylint: disable=unused-argument
        ) -> None:
    '''Sets conversion flags according to the given version that we are
    converting from.
    '''

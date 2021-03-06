# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, Optional

from softfab.configlib import ConfigDB
from softfab.utils import pluralize


def configsUsingTaskDef(configDB: ConfigDB, taskDefId: str) -> Iterator[str]:
    '''Iterates through the IDs of those configurations that contain the given
    task definition.
    '''
    for configId, config in configDB.items():
        if config.getTask(taskDefId) is not None:
            yield configId

def formatTimeout(timeout: Optional[int]) -> str:
    '''Returns a description of the given timeout value.
    '''
    if timeout is None:
        return 'never'
    else:
        return f"{timeout:d} {pluralize('minute', timeout)}"

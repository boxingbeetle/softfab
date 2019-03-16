# SPDX-License-Identifier: BSD-3-Clause

from softfab.configlib import configDB
from softfab.utils import pluralize


def configsUsingTaskDef(taskDefId):
    '''Iterates through the IDs of those configurations that contain the given
    task definition.
    '''
    for configId, config in configDB.items():
        if config.getTask(taskDefId) is not None:
            yield configId

def formatTimeout(timeout):
    '''Returns a description of the given timeout value.
    '''
    if timeout is None:
        return 'never'
    else:
        return '%d %s' % (timeout, pluralize('minute', timeout))

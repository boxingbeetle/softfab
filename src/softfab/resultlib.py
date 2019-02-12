# SPDX-License-Identifier: BSD-3-Clause

import os.path
import re
from typing import Iterator, Mapping, Sequence, Set, Tuple

from softfab.config import dbDir
from softfab.taskrunlib import taskRunDB

syntheticKeys = ( 'sf.duration', )

# Values are stored in "results/<taskdef>/<key>/<taskrun>".
_dbDir = dbDir + '/results'

# Regular expression which defines all valid keys.
# TODO: Are these the characters we want to support?
# TODO: Are they by definition equal to databaselib._reKey? If so, refactor.
_reKey = re.compile('^[A-Za-z0-9+_-][A-Za-z0-9.+_ -]*$')

def getData(taskName: str, runIds: Sequence[str], key: str) \
        -> Iterator[Tuple[str, str]]:
    '''Creates a generator that returns pairs (run, value) for all of the
    given runs that have a value stored in the results database.
    The returned values are in the same order as in the given runIds.
    The runIds are not checked against malicious constructs, so the caller
    should take care that they are secure.
    '''
    # Handle synthetic keys.
    if key in syntheticKeys:
        if key == 'sf.duration':
            # This info is in the job DB, but we cannot access it there because
            # there is no mapping from task run ID to job.
            for run in runIds:
                yield run, str(taskRunDB[run]['duration'])
            return
        raise NotImplementedError(key)

    # Handle user keys.
    valueDir = _dbDir + '/' + taskName + '/' + key + '/'
    for run in runIds:
        try:
            with open(valueDir + run) as inp:
                value = inp.readline()
            yield run, value
        except IOError:
            # Not all runs are guaranteed to have values stored.
            pass

def putData(taskName: str, runId: str, data: Mapping[str, str]) -> None:
    '''Stores the data from a task run in the results database.
    The keys are checked against malicious constructs.
    '''
    # Check all keys before committing anything.
    for key in data.keys():
        if _reKey.match(key) is None:
            raise KeyError('Invalid character in key "%s".' % key)

    taskDir = _dbDir + '/' + taskName + '/'
    # Remove old data.
    for key in getKeys(taskName):
        if key not in data:
            path = taskDir + key + '/' + runId
            if os.path.exists(path):
                os.remove(path)
    # Insert new data.
    for key, value in data.items():
        keyDir = taskDir + key
        if not os.path.exists(keyDir):
            os.makedirs(keyDir)
        with open(keyDir + '/' + runId, 'w') as out:
            out.write(value)

def getKeys(taskName: str) -> Set[str]:
    '''Gets the set of keys that exist for the given task name.
    The existance of a key means that at least one record contains that key;
    it is not guaranteed all records will contain that key.
    '''
    keys = set(('sf.duration',))
    path = _dbDir + '/' + taskName
    if os.path.exists(path):
        keys.update(os.listdir(path))
    return keys

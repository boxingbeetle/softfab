# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterable, Iterator, Mapping, Set, Tuple
import os.path
import re

from softfab.config import dbDir

# Values are stored in "results/<taskdef>/<key>/<taskrun>".
_dbDir = dbDir + '/results'

# Regular expression which defines all valid keys.
# TODO: Are these the characters we want to support?
# TODO: Are they by definition equal to databaselib._reKey? If so, refactor.
_reKey = re.compile('^[A-Za-z0-9+_-][A-Za-z0-9.+_ -]*$')

def getCustomKeys(taskName: str) -> Set[str]:
    '''Get the set of used-defined keys that exist for the given task name.
    The existance of a key means that at least one record contains that key;
    it is not guaranteed all records will contain that key.
    '''
    path = _dbDir + '/' + taskName
    keys = set()
    if os.path.exists(path):
        keys.update(os.listdir(path))
    return keys

def getCustomData(taskName: str,
                  runIds: Iterable[str],
                  key: str
                  ) -> Iterator[Tuple[str, str]]:
    '''Yield (run, value) pairs for all of the given runs that have
    a user-defined value stored in the results database.
    The returned values are in the same order as in the given runIds.
    The runIds are not checked against malicious constructs, so the caller
    should take care that they are secure.
    '''
    valueDir = _dbDir + '/' + taskName + '/' + key + '/'
    for run in runIds:
        try:
            with open(valueDir + run) as inp:
                value = inp.readline()
            yield run, value
        except OSError:
            # Not all runs are guaranteed to have values stored.
            pass

def putData(taskName: str, runId: str, data: Mapping[str, str]) -> None:
    '''Stores the data from a task run in the results database.
    The keys are checked against malicious constructs.
    '''
    # Check all keys before committing anything.
    for key in data.keys():
        if _reKey.match(key) is None:
            raise KeyError(f'Invalid character in key "{key}".')

    # Insert new data.
    taskDir = _dbDir + '/' + taskName + '/'
    for key, value in data.items():
        keyDir = taskDir + key
        if not os.path.exists(keyDir):
            os.makedirs(keyDir)
        with open(keyDir + '/' + runId, 'w') as out:
            out.write(value)

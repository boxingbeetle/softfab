# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, cast
import logging

from softfab.config import dbDir
from softfab.databaselib import (
    Database, DatabaseElem, RecordObserver, createUniqueId
)
from softfab.resultcode import ResultCode
from softfab.sortedqueue import SortedQueue
from softfab.storagelib import StorageURLMixin
from softfab.timelib import getTime
from softfab.utils import abstract, cachedProperty
from softfab.xmlbind import XMLTag
from softfab.xmlgen import xml

# Note: To avoid cyclic imports, taskrunlib sets this.
#       The weird construct is to avoid PyLint complaining about methods we
#       call on it not existing for NoneType.
taskRunDB = cast(Database, (lambda x: x if x else None)(0))

class ShadowFactory:
    @staticmethod
    def createExtraction(attributes):
        return ExtractionRun(attributes)

class ShadowDB(Database):
    baseDir = dbDir + '/shadow'
    factory = ShadowFactory()
    privilegeObject = 'sh'
    description = 'shadow run'
    uniqueKeys = ( 'shadowId', )
shadowDB = ShadowDB()

# Note: Order of inheritance is important: XMLTag's (implemented) version of
#       toXML should be called instead of DatabaseElem's (abstract) version.
class ShadowRun(XMLTag, DatabaseElem, StorageURLMixin):
    '''Abstract base class for elements in the shadow queue.

    Each subclass should set its own value for "tagName", corresponding to
    the name of the "create*" method in ShadowFactory.

    At some point, this class could be integrated with TaskRun, but I prefer
    to wait for this code to reach some level of maturity first.
    '''
    tagName = abstract # type: ClassVar[str]
    intProperties = ('createtime', 'starttime', 'stoptime')
    enumProperties = {'result': ResultCode}

    @classmethod
    def _create(cls, **extraAttributes):
        attributes = {
            'shadowId': createUniqueId(),
            'createtime': getTime(),
            'state': 'waiting',
            }
        attributes.update(extraAttributes)
        return cls(attributes)

    def __init__(self, attributes):
        XMLTag.__init__(self, attributes)
        DatabaseElem.__init__(self)
        StorageURLMixin.__init__(self)

    def __getitem__(self, key):
        if key == '-createtime':
            return -self._properties['createtime']
        elif key == 'duration':
            startTime = self._properties.get('starttime')
            stopTime = self._properties.get('stoptime') or getTime()
            if startTime is None:
                return None
            else:
                return stopTime - startTime
        elif key == 'description':
            return self.getDescription()
        elif key == 'location':
            return self.getLocation()
        else:
            return XMLTag.__getitem__(self, key)

    def _canBeRunOn(self, taskRunner):
        '''Returns true iff this shadow run can be executed on the given
        Task Runner.
        '''
        raise NotImplementedError

    def getId(self):
        return self._properties['shadowId']

    def getDescription(self):
        '''Returns a human-readable desription of this shadow run.
        '''
        raise NotImplementedError

    def getLocation(self):
        '''Returns a human-readable description of where this shadow run
        will execute. This is related to _canBeRunOn.
        A location can be a Task Runner, but in the future it could also
        be a storage pool (for cleanup tasks, for example).
        '''
        raise NotImplementedError

    def hasExpired(self):
        '''Returns True iff this record is either obsolete or pointing to
        other records that no longer exist.
        Expired records will be removed when the database is loaded.
        '''
        return False

    def isWaiting(self):
        return self._properties['state'] == 'waiting'

    def isRunning(self):
        return self._properties['state'] == 'running'

    def isDone(self):
        return self._properties['state'] == 'done'

    def isToBeAborted(self):
        # TODO: Implement user abort for shadow tasks.
        return False

    def getResult(self):
        '''Gets the ResultCode (OK, WARNING, ERROR),
        or None if there is no result yet.
        '''
        return self._properties.get('result')

    def getTaskRunnerId(self):
        '''Returns the ID of the Task Runner that is or was running this shadow
        run, or None if this shadow run has not been assigned yet.
        '''
        return self._properties.get('taskrunner')

    def assign(self, taskRunner):
        '''Attempt to assign this shadow run for execution on the given
        Task Runner.
        @return True iff assignment succeeded.
        '''

        # Check whether this is a capable Task Runner.
        if not self._canBeRunOn(taskRunner):
            return False

        # State validation.
        assert self._properties['state'] == 'waiting', self._properties['state']

        self._properties['state'] = 'running'
        self._properties['starttime'] = getTime()
        self._properties['taskrunner'] = taskRunner.getId()
        self._notify()
        return True

    def done(self, result):
        # Input validation.
        if result not in (
            ResultCode.OK, ResultCode.WARNING, ResultCode.ERROR
            ):
            raise ValueError('"%s" is not a valid result code' % result)

        # State validation.
        if self._properties['state'] != 'running':
            # If this shadow task was not running, it cannot finish either.
            # TODO: This should not happen, so log this incident.
            # TODO: Or should we raise an exception instead?
            return

        self._properties['state'] = 'done'
        self._properties['stoptime'] = getTime()
        self._properties['result'] = result
        self._notify()

    def failed(self, message): # pylint: disable=unused-argument
        '''Marks this run as failed.
        Used when a Task Runner is not behaving like it should, for example
        the Task Runner is lost.
        '''
        # TODO: There is no way to get the error message to the user.
        self.done(ResultCode.ERROR)

class ExtractionRun(ShadowRun):
    '''A mid-level data extraction.
    '''
    tagName = 'extraction'

    @classmethod
    def create(cls, taskRun):
        return cls._create(
            taskRun = taskRun.getId(),
            runner = taskRun['runner']
            )

    # Delayed initialisation is required because we have a circular dependency.
    @cachedProperty
    def taskRun(self):
        '''Gets the task run of which the data should be extracted.
        '''
        return taskRunDB[self._properties['taskRun']]

    def _canBeRunOn(self, taskRunner):
        # Extraction runs are bound to a specific TR.
        return self._properties['runner'] == taskRunner.getId()

    def hasExpired(self):
        return self._properties['taskRun'] not in taskRunDB

    def getDescription(self):
        return 'Extract %s' % self.taskRun.getName()

    def getLocation(self):
        return self._properties['runner']

    def externalize(self):
        '''Returns an XMLNode containing info the Task Runner needs to perform
        this extraction run.
        See the sync protocol documentation.
        '''
        taskRun = self.taskRun
        return xml.extract[
            xml.shadowrun(shadowId = self.getId()),
            taskRun.createRunXML(),
            taskRun.createTaskXML(),
            taskRun.createInputXML()
            ]

class OKShadowRuns(SortedQueue):
    compareField = '-createtime'

    def _filter(self, record):
        return record.getResult() is ResultCode.OK

class DoneShadowRuns(SortedQueue):
    compareField = '-createtime'

    def _filter(self, record):
        return record.isDone()

maxOKRecords = 10
maxDoneRecords = 50

class RecordTrimmer(RecordObserver):

    def __init__(self):
        RecordObserver.__init__(self)
        self.__okShadowRuns = OKShadowRuns(shadowDB)
        self.__doneShadowRuns = DoneShadowRuns(shadowDB)

        # Initial trim, in case the policies have changed.
        self.__trimRecords()

        shadowDB.addObserver(self)

    def added(self, record):
        self.__trimRecords()

    def removed(self, record):
        # Removed records only make the list shorter, so no need to trim.
        pass

    def updated(self, record):
        self.__trimRecords()

    def __trimRecords(self):
        '''Remove old records: they are unlikely to be relevant anymore and
        keeping them takes up space in memory and in the visualisation.
        '''
        if len(self.__okShadowRuns) > maxOKRecords:
            for record in list(self.__okShadowRuns)[maxOKRecords : ]:
                shadowDB.remove(record)
        if len(self.__doneShadowRuns) > maxDoneRecords:
            for record in list(self.__doneShadowRuns)[maxDoneRecords : ]:
                shadowDB.remove(record)

def _removeExpiredRecords():
    '''Removes expired records from the shadow queue.
    In normal operation records will not expire, but if the database got
    corrupted or records were manually deleted, it will help in getting back
    to a consistent state.
    '''
    expiredRuns = [run for run in shadowDB if run.hasExpired()]
    for shadowRun in expiredRuns:
        logging.warning('Removing expired shadow run %s', shadowRun.getId())
        shadowDB.remove(shadowRun)

def startShadowRunCleanup():
    """Starts automatic cleanup of shadow runs.
    Must be called after database preloading.
    """
    _removeExpiredRecords()
    RecordTrimmer()

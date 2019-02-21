# SPDX-License-Identifier: BSD-3-Clause

from softfab.config import dbDir
from softfab.databaselib import (
    Database, SingletonElem, SingletonObserver, SingletonWrapper
    )
from softfab.timelib import getTime
from softfab.userlib import userDB
from softfab.utils import cachedProperty
from softfab.version import version
from softfab.xmlbind import XMLTag
from softfab.xmlgen import xml

from enum import Enum
import logging
import os
import os.path
import re
import time

# Check for pytz (package python-tz in Debian).
# Full SoftFab installations should have this, but by making it optional it
# is easier to set up a development system.
try:
    import pytz
except ImportError:
    HAVE_PYTZ = False
else:
    HAVE_PYTZ = True

EmbeddingPolicy = Enum('EmbeddingPolicy', 'NONE SELF CUSTOM')

def _guessSystemTimezone():
    '''Makes a best effort to determine the system timezone.
    Returns either a member of pytz.common_timezones or the empty string.
    '''
    if not HAVE_PYTZ:
        return ''

    # Use the timezone as reported by Python.
    # It is likely to report "CET" instead of "Europe/Amsterdam" though.
    timezone = time.tzname[0]
    if '/' in timezone and timezone in pytz.common_timezones:
        return timezone

    # Debian stores the timezone in /etc/timezone.
    try:
        lines = open('/etc/timezone').readlines()
    except IOError:
        pass
    else:
        if lines:
            timezone = lines[0].strip()
            if timezone in pytz.common_timezones:
                return timezone

    # SUSE and Red Hat configure the timezone using /etc/sysconfig/clock.
    try:
        lines = open('/etc/sysconfig/clock').readlines()
    except IOError:
        pass
    else:
        reTimezone = re.compile(
            r'^\s*TIMEZONE\s*=\s*["\']?([A-Za-z_\-/]*)["\']?\s*(#.*)?$'
            )
        for line in lines:
            match = reTimezone.match(line)
            if reTimezone.match(line):
                timezone = match.group(1)
                if timezone in pytz.common_timezones:
                    return timezone

    # In Mac OS X, /etc/localtime is a symlink to the timezone definition.
    # (In Linux, it seems to be a hardlink or copy instead.)
    if os.path.islink('/etc/localtime'):
        parts = os.readlink('/etc/localtime').rsplit('/', 2)
        if len(parts) == 3:
            timezone = parts[-2] + '/' + parts[-1]
            if timezone in pytz.common_timezones:
                return timezone

    # Give up.
    return ''

def _selectTimezone():
    timezone = project['timezone']
    if timezone:
        os.environ['TZ'] = timezone
        if hasattr(time, 'tzset'):
            time.tzset()
        else:
            # time.tzset() is not available on Windows.
            logging.warning(
                'Could not change time zone because this platform does not '
                'provide time.tzset().'
                )

def getKnownTimezones():
    if HAVE_PYTZ:
        return pytz.common_timezones
    else:
        return ()

defaultMaxJobs = 25

class ProjectFactory:
    def createProject(self, attributes):
        return Project(attributes)

class ProjectDB(Database):
    baseDir = dbDir + '/project'
    factory = ProjectFactory()
    privilegeObject = 'p'
    description = 'project configuration'
    keepInMemoryDuringConversion = True
_projectDB = ProjectDB()

class Project(XMLTag, SingletonElem):
    '''Overall project settings.
    '''
    tagName = 'project'
    boolProperties = ('taskprio', 'trselect', 'reqtag', 'anonguest')
    intProperties = ('maxjobs', )
    enumProperties = {'embed': EmbeddingPolicy}

    def __init__(self, properties):
        XMLTag.__init__(self, properties)
        SingletonElem.__init__(self)
        self._properties.setdefault('maxjobs', defaultMaxJobs)
        self._properties.setdefault('embed', EmbeddingPolicy.NONE)
        self._properties.setdefault('embedcustom', '')
        if not self._properties.get('timezone'):
            self._properties['timezone'] = _guessSystemTimezone()

        self.__targets = set()
        # Note: tag keys should be kept in a list rather than a set,
        # because the order of tag keys everywhere in the UI should be the
        # same as specified in the project configuration (rather than sorted
        # alphabetically). This allows the project to choose which tag they
        # have as the first one (and thus the default and the mostly used one).
        self.__tagKeys = []

    def _addTarget(self, attributes):
        self.__targets.add(attributes['name'])

    def _addTagkey(self, attributes):
        self.__tagKeys.append(attributes['key'])

    def getTargets(self):
        return set(self.__targets or [ 'unknown' ])

    def setTargets(self, targets):
        self.__targets = set(targets)

    def getTagKeys(self):
        return self.__tagKeys

    def setTagKeys(self, tagKeys):
        self.__tagKeys = list(tagKeys)

    @property
    def showOwners(self):
        """Should owners be shown in the user interface?

        Returns True iff there are multiple active users.
        """
        return userDB.numActiveUsers > 1

    @property
    def showTargets(self):
        """Should targets be shown in the user interface?

        Returns True iff more than one target is defined.
        """
        return len(self.__targets) > 1

    def getResourceServer(self):
        return self._properties.get('resources')

    def setAnonGuestAccess(self, enabled: bool) -> None:
        """Changes the anonymous guest access setting.

        The change is immediately committed to the database.
        """
        self._properties['anonguest'] = bool(enabled)
        self._notify()

    def updateVersion(self):
        '''Indicates that the database format is up-to-date.
        Used by "upgrade.py" to save version of the last upgrade.
        '''
        self._properties['version'] = version
        self._notify()

    def _getContent(self):
        for name in self.__targets:
            yield xml.target( name = name)
        for name in self.__tagKeys:
            yield xml.tagKey(key = name)

    @cachedProperty
    def frameAncestors(self):
        """Pattern that specifies which sites are allowed to embed this
        Control Center in a page.
        """
        embed = self._properties['embed']
        if embed is EmbeddingPolicy.NONE:
            return "'none'"
        elif embed is EmbeddingPolicy.SELF:
            return "'self'"
        elif embed is EmbeddingPolicy.CUSTOM:
            return self._properties['embedcustom']
        else:
            assert False, embed
            return "'none'"

# Create singleton record if it doesn't exist already.
if len(_projectDB) == 0:
    _project = Project( { 'name': 'Nameless' } )
    _project.updateVersion()
    _projectDB.add(_project)
    del _project

project = SingletonWrapper(_projectDB)

class _TimezoneUpdater(SingletonObserver):

    def updated(self, record):
        _selectTimezone()

_selectTimezone()
_projectDB.addObserver(_TimezoneUpdater())

_bootTime = getTime()
def getBootTime():
    return _bootTime

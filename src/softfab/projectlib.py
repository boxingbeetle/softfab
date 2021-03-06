# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from getpass import getuser
from pathlib import Path
from socket import getfqdn
from typing import (
    AbstractSet, Iterable, List, Mapping, MutableSet, Sequence, cast
)
import logging
import os
import os.path
import time

from softfab.databaselib import Database, SingletonElem, SingletonObserver
from softfab.timelib import getTime
from softfab.users import AnonGuestUser, UnknownUser, User
from softfab.utils import cachedProperty
from softfab.version import VERSION
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLAttributeValue, XMLContent, xml

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

def _guessSystemTimezone() -> str:
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

    # In macOS and in Linux distros using systemd, /etc/localtime is a symlink
    # to the timezone definition.
    if os.path.islink('/etc/localtime'):
        parts = os.readlink('/etc/localtime').rsplit('/', 2)
        if len(parts) == 3:
            timezone = parts[-2] + '/' + parts[-1]
            if timezone in pytz.common_timezones:
                return timezone

    # Give up.
    return ''

def _selectTimezone(timezone: str) -> None:
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

def getKnownTimezones() -> Sequence[str]:
    if HAVE_PYTZ:
        return pytz.common_timezones
    else:
        return ()

defaultFactoryName = 'Nameless'
defaultMaxJobs = 25

class Project(XMLTag, SingletonElem):
    '''Overall project settings.
    '''
    tagName = 'project'
    boolProperties = ('taskprio', 'anonguest', 'mailnotification')
    intProperties = ('maxjobs', )
    enumProperties = {'embed': EmbeddingPolicy}

    def __init__(self, properties: Mapping[str, XMLAttributeValue]):
        super().__init__(properties)
        self._properties.setdefault('maxjobs', defaultMaxJobs)
        self._properties.setdefault('embed', EmbeddingPolicy.NONE)
        self._properties.setdefault('embedcustom', '')
        if not self._properties.get('timezone'):
            self._properties['timezone'] = _guessSystemTimezone()
        if 'smtprelay' not in self._properties:
            self._properties['smtprelay'] = 'localhost'
        if 'mailsender' not in self._properties:
            self._properties['mailsender'] = f'{getuser()}@{getfqdn()}'

        self.__targets: MutableSet[str] = set()
        # Note: tag keys should be kept in a list rather than a set,
        # because the order of tag keys everywhere in the UI should be the
        # same as specified in the project configuration (rather than sorted
        # alphabetically). This allows the project to choose which tag they
        # have as the first one (and thus the default and the mostly used one).
        self.__tagKeys: List[str] = []

    def _addTarget(self, attributes: Mapping[str, str]) -> None:
        self.__targets.add(attributes['name'])

    def _addTagkey(self, attributes: Mapping[str, str]) -> None:
        self.__tagKeys.append(attributes['key'])

    def getTargets(self) -> AbstractSet[str]:
        return self.__targets

    def setTargets(self, targets: Iterable[str]) -> None:
        self.__targets = set(targets)

    def getTagKeys(self) -> Sequence[str]:
        return self.__tagKeys

    def setTagKeys(self, tagKeys: Iterable[str]) -> None:
        self.__tagKeys = list(tagKeys)

    @property
    def showTargets(self) -> bool:
        """Should targets be shown in the user interface?

        Returns True iff at least one target is defined.
        """
        return bool(self.__targets)

    @property
    def name(self) -> str:
        """User-given name of this project.
        """
        return cast(str, self._properties['name'])

    @property
    def timezone(self) -> str:
        """Name of the main time zone for this project,
        or the empty string if the time zone is unknown.
        """
        return cast(str, self._properties['timezone'])

    @property
    def smtpRelay(self) -> str:
        """SMTP relay to send outgoing messages to.
        """
        return cast(str, self._properties['smtprelay'])

    @property
    def mailSender(self) -> str:
        """Sender address (From:) to be used in outgoing messages.
        """
        return cast(str, self._properties['mailsender'])

    def setMailConfig(self,
            enabled: bool, smtpRelay: str, mailSender: str
            ) -> None:
        """Changes the e-mail send settings.

        The change is immediately committed to the database.
        """
        self._properties['mailnotification'] = enabled
        self._properties['smtprelay'] = smtpRelay
        self._properties['mailsender'] = mailSender
        self._notify()

    @property
    def defaultUser(self) -> User:
        """The user object when an unauthenticated request is made.
        """
        return AnonGuestUser() if self['anonguest'] else UnknownUser()

    @property
    def anonguest(self) -> bool:
        """Is anonymous guest access enabled?
        When enabled, non-authenticated requests get guest privileges
        rather than no privileges.
        """
        return cast(bool, self._properties['anonguest'])

    def setAnonGuestAccess(self, enabled: bool) -> None:
        """Changes the anonymous guest access setting.

        The change is immediately committed to the database.
        """
        self._properties['anonguest'] = bool(enabled)
        self._notify()

    @property
    def dbVersion(self) -> str:
        """SoftFab version at which the database was last migrated."""
        return cast(str, self._properties['version'])

    def updateVersion(self) -> None:
        '''Indicates that the database format is up-to-date.
        Used by "upgrade.py" to save version of the last upgrade.
        '''
        self._properties['version'] = VERSION
        self._notify()

    def _getContent(self) -> XMLContent:
        for name in self.__targets:
            yield xml.target( name = name)
        for name in self.__tagKeys:
            yield xml.tagKey(key = name)

    @cachedProperty
    def frameAncestors(self) -> str:
        """Pattern that specifies which sites are allowed to embed this
        Control Center in a page.
        """
        embed = self._properties['embed']
        if embed is EmbeddingPolicy.NONE:
            return "'none'"
        elif embed is EmbeddingPolicy.SELF:
            return "'self'"
        elif embed is EmbeddingPolicy.CUSTOM:
            return cast(str, self._properties['embedcustom'])
        else:
            assert False, embed
            return "'none'"

class ProjectFactory:
    def createProject(self, attributes: Mapping[str, str]) -> Project:
        return Project(attributes)

class ProjectDB(Database[Project]):
    privilegeObject = 'p'
    description = 'project configuration'

    def __init__(self, baseDir: Path):
        super().__init__(baseDir, ProjectFactory())

    def _postLoad(self) -> None:
        super()._postLoad()

        # Create singleton record if it doesn't exist already.
        if len(self) == 0:
            record = Project({'name': defaultFactoryName})
            record.updateVersion()
            self.add(record)

class TimezoneUpdater(SingletonObserver):

    def updated(self, record: Project) -> None:
        _selectTimezone(record.timezone)

_bootTime = getTime()
def getBootTime() -> int:
    return _bootTime

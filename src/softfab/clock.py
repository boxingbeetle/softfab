# SPDX-License-Identifier: BSD-3-Clause

from softfab.statuslib import StatusModel, StatusModelRegistry
from softfab.xmlgen import xml

from twisted.internet import reactor
from time import localtime, strftime

# TODO: Make separate model for second-accuracy and minute-accuracy clock.
#       The latter is needed for updating the clock in the bottom bar if we
#       no longer do page refreshes.
# TODO: Use the minute-accuracy clock to trigger schedules.
class ClockModel(StatusModel):
    '''Model which is convenient for testing.

    Command line:
      wget --no-proxy -q -O - \
        'http://host/path/ObserveStatus?model=clock/local&format=iso8601'
    Substitute "-S" for "-q" to test error handling.
    '''
    __delayedCall  = None

    @classmethod
    def getChildClass(cls):
        return None

    def __update(self):
        self._notify()
        self.__delayedCall = reactor.callLater(1, self.__update)

    def _registerForUpdates(self):
        self.__delayedCall = reactor.callLater(1, self.__update)

    def _unregisterForUpdates(self):
        self.__delayedCall.cancel()

    def formatIso8601(self):
        return xml.status(
            time = strftime('%Y-%m-%d %H:%M:%S', self.getTime())
            )

    def getTime(self):
        return localtime()

class ClockModelGroup(StatusModel):

    @classmethod
    def getChildClass(cls):
        return ClockModel

    def _createModel(self, key):
        if key == 'local':
            return ClockModel(key, self)
        else:
            raise KeyError(key)

    def _iterKeys(self):
        yield 'local'

    def _registerForUpdates(self):
        # The set of children is fixed.
        pass

    def _unregisterForUpdates(self):
        pass

StatusModelRegistry.instance.addModelGroup(ClockModelGroup, 'clock')

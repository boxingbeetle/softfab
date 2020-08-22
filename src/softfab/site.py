# SPDX-License-Identifier: BSD-3-Clause

from os import getpid
from pathlib import Path

from twisted.internet.endpoints import clientFromString
from twisted.internet.interfaces import IReactorUNIX, IStreamClientEndpoint
from twisted.web.client import URI
from twisted.web.iweb import IAgentEndpointFactory
from twisted.web.server import Session, Site
from zope.interface import implementer


class LongSession(Session):
    sessionTimeout = 60 * 60 * 24 * 7 # one week in seconds

class ControlCenter(Site):
    sessionFactory = LongSession

    secureCookie: bool
    """Mark session cookie as secure.
    When True, the browser will only transmit it over HTTPS.
    """

    def __repr__(self) -> str:
        return 'ControlCenter'

class ControlSocket(Site):

    def __repr__(self) -> str:
        return 'ControlSocket'

@implementer(IAgentEndpointFactory)
class ControlSocketFactory:

    def __init__(self, reactor: IReactorUNIX, path: Path):
        self.reactor = reactor
        self.path = path

    def endpointForURI(self,
                       uri: URI # pylint: disable=unused-argument
                       ) -> IStreamClientEndpoint:
        """Return an endpoint for contacting the Control Center.
        Raise OSError if there is no control socket in the data directory.
        """

        socketPath = (self.path / 'ctrl.sock').resolve()
        if socketPath.is_socket():
            return clientFromString(self.reactor,
                                    f'unix:{socketPath}:timeout=10')
        else:
            raise OSError(f"Control socket not found: {socketPath}")

def writePIDFile(path: Path) -> None:
    """Write our process ID to a text file.
    Raise OSError if writing the file failed.
    """
    with open(path, 'w', encoding='utf-8') as out:
        out.write(f'{getpid():d}\n')

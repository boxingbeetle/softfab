# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Type

from softfab.Page import ArgT, Authenticator, FabResource, ProcT, Responder
from softfab.authentication import HTTPAuthPage


class _ErrorResponder(Responder):

    def respond(self, response, proc):
        response.setStatus(500, 'Unexpected exception processing request')
        response.setHeader('Content-Type', 'text/plain')
        response.write(
            'Unexpected exception processing request.\n'
            'Details were written to the server log.\n'
            )

plainTextErrorResponder = _ErrorResponder()

class ControlPage(FabResource[ArgT, ProcT], Responder):
    '''Base class for resources that allow processes to talk to the Control
    Center. Such processes include our clients (Task Runner, Notifier) and
    third party processes (through API calls).
    '''
    contentType = 'text/xml; charset=UTF-8'
    authenticator = HTTPAuthPage # type: ClassVar[Type[Authenticator]]

    def getContentType(self, proc): # pylint: disable=unused-argument
        return self.contentType

    def errorResponder(self, ex: Exception) -> Responder:
        return plainTextErrorResponder

    def respond(self, response, proc):
        response.setHeader('Content-Type', self.getContentType(proc))
        return self.writeReply(response, proc)

    def writeReply(self, response, proc):
        raise NotImplementedError

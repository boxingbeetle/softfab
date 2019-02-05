# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Type

from Page import Authenticator, FabResource, Responder
from authentication import HTTPAuthPage

class _ErrorResponder(Responder):

    def respond(self, response, proc):
        response.setStatus(500, 'Unexpected exception processing request')
        response.setHeader('Content-Type', 'text/plain')
        response.write(
            'Unexpected exception processing request.\n'
            'Details were written to the server log.\n'
            )

class ControlPage(FabResource, Responder):
    '''Base class for resources that allow processes to talk to the Control
    Center. Such processes include our clients (Task Runner, Notifier) and
    third party processes (through API calls).
    '''
    contentType = 'text/xml; charset=UTF-8'
    authenticationWrapper = HTTPAuthPage # type: ClassVar[Type[Authenticator]]

    __errorResponder = _ErrorResponder()

    def getContentType(self, proc): # pylint: disable=unused-argument
        return self.contentType

    def errorResponder(self, ex):
        return self.__errorResponder

    def respond(self, response, proc):
        response.setHeader('Content-Type', self.getContentType(proc))
        return self.writeReply(response, proc)

    def writeReply(self, response, proc):
        raise NotImplementedError

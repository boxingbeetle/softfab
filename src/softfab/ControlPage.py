# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar, Generic, Optional, Type

from softfab.Page import (
    Authenticator, FabResource, PageProcessor, ProcT, Responder
)
from softfab.authentication import HTTPAuthPage
from softfab.pageargs import ArgsT


class ControlResponder(Responder, Generic[ArgsT, ProcT]):

    def __init__(self, page: 'ControlPage[ArgsT, ProcT]', proc: ProcT):
        super().__init__()
        self.page = page
        self.proc = proc

    def respond(self, response):
        page = self.page
        proc = self.proc
        response.setHeader('Content-Type', page.getContentType(proc))
        return page.writeReply(response, proc)

class _ErrorResponder(Responder):

    def respond(self, response):
        response.setStatus(500, 'Unexpected exception processing request')
        response.setHeader('Content-Type', 'text/plain')
        response.write(
            'Unexpected exception processing request.\n'
            'Details were written to the server log.\n'
            )

plainTextErrorResponder = _ErrorResponder()

class ControlPage(FabResource[ArgsT, ProcT]):
    '''Base class for resources that allow processes to talk to the Control
    Center. Such processes include our clients (Task Runner, Notifier) and
    third party processes (through API calls).
    '''
    contentType = 'text/xml; charset=UTF-8'
    authenticator = HTTPAuthPage # type: ClassVar[Type[Authenticator]]

    def getResponder(self, path: Optional[str], proc: ProcT) -> Responder:
        if path is None:
            return ControlResponder(self, proc)
        else:
            raise KeyError('Resource does not contain subitems')

    def getContentType(self, proc): # pylint: disable=unused-argument
        return self.contentType

    def errorResponder(self, ex: Exception, proc: PageProcessor) -> Responder:
        return plainTextErrorResponder

    def writeReply(self, response, proc):
        raise NotImplementedError

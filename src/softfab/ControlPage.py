# SPDX-License-Identifier: BSD-3-Clause

from typing import Generic, Optional

from softfab.Page import Authenticator, FabResource, ProcT, Responder
from softfab.authentication import HTTPAuthPage
from softfab.pageargs import ArgsT
from softfab.response import Response


class ControlResponder(Responder, Generic[ArgsT, ProcT]):

    def __init__(self, page: 'ControlPage[ArgsT, ProcT]', proc: ProcT):
        super().__init__()
        self.page = page
        self.proc = proc

    async def respond(self, response: Response) -> None:
        page = self.page
        proc = self.proc
        response.setContentType(page.getContentType(proc))
        await page.writeReply(response, proc)

class _ErrorResponder(Responder):

    async def respond(self, response: Response) -> None:
        response.setStatus(500, 'Unexpected exception processing request')
        response.setContentType('text/plain')
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
    authenticator: Authenticator = HTTPAuthPage.instance

    def getResponder(self, path: Optional[str], proc: ProcT) -> Responder:
        if path is None:
            return ControlResponder(self, proc)
        else:
            raise KeyError('Resource does not contain subitems')

    def getContentType(self, proc: ProcT) -> str: # pylint: disable=unused-argument
        return self.contentType

    def errorResponder(self, ex: Exception, proc: ProcT) -> Responder:
        return plainTextErrorResponder

    async def writeReply(self, response: Response, proc: ProcT) -> None:
        raise NotImplementedError

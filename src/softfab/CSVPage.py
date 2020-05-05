# SPDX-License-Identifier: BSD-3-Clause

'''Export data in CSV format
'''

from typing import Generic, Iterator, Optional, Sequence

from softfab.ControlPage import plainTextErrorResponder
from softfab.Page import FabResource, ProcT, Responder
from softfab.authentication import LoginAuthPage
from softfab.pagelinks import CSVArgs, CSVSeparator
from softfab.response import Response
from softfab.webgui import pageLink
from softfab.xmlgen import XML, xhtml


class CSVResponder(Responder, Generic[ProcT]):

    def __init__(self, page: 'CSVPage[ProcT]', proc: ProcT):
        super().__init__()
        self.page = page
        self.proc = proc

    async def respond(self, response: Response) -> None:
        page = self.page
        proc = self.proc
        response.setContentType('text/x-csv; charset=UTF-8')
        response.setFileName(page.getFileName(proc))
        sepChar = proc.args.sep.value
        for row in page.iterRows(proc):
            response.write(sepChar.join(row) + '\r\n')

class CSVPage(FabResource['CSVPage.Arguments', ProcT]):
    authenticator = LoginAuthPage.instance

    class Arguments(CSVArgs):
        pass

    def getResponder(self, path: Optional[str], proc: ProcT) -> Responder:
        if path is None:
            return CSVResponder(self, proc)
        else:
            raise KeyError('Resource does not contain subitems')

    def errorResponder(self, ex: Exception, proc: ProcT) -> Responder:
        return plainTextErrorResponder

    def getFileName(self, proc: ProcT) -> str:
        raise NotImplementedError

    def iterRows(self, proc: ProcT) -> Iterator[Sequence[str]]:
        raise NotImplementedError

def presentCSVLink(page: str, args: CSVArgs) -> XML:
    return xhtml.p[
        'Export data in CSV format: ',
        pageLink(page, args.override(sep=CSVSeparator.COMMA))['comma'],
        ' or ',
        pageLink(page, args.override(sep=CSVSeparator.SEMICOLON))['semicolon'],
        ' separated',
        xhtml.br,
        'Note: Excel only accepts the list separator from the OS regional '
        'settings.'
        ]

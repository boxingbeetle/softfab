# SPDX-License-Identifier: BSD-3-Clause

'''Export data in CSV format
'''

from enum import Enum
from typing import Generic, Iterator, Optional, Sequence

from softfab.ControlPage import plainTextErrorResponder
from softfab.Page import FabResource, PageProcessor, ProcT, Responder
from softfab.authentication import LoginAuthPage
from softfab.pageargs import EnumArg, PageArgs
from softfab.response import Response
from softfab.webgui import pageLink
from softfab.xmlgen import XML, xhtml


class Separator(Enum):
    '''Identifies the separator character to place between values.
    The reason for allowing different separator characters than the comma is
    that Excel only accepts the separator character of the active locale.
    This is an utterly stupid idea, but many people use Excel so we have to
    work around its idiocies.
    '''
    COMMA = ','
    SEMICOLON = ';'
    TAB = '\t'

class CSVResponder(Responder, Generic[ProcT]):

    def __init__(self, page: 'CSVPage[ProcT]', proc: ProcT):
        super().__init__()
        self.page = page
        self.proc = proc

    def respond(self, response: Response) -> None:
        page = self.page
        proc = self.proc
        response.setHeader('Content-Type', 'text/x-csv; charset=UTF-8')
        response.setFileName(page.getFileName(proc))
        sepChar = proc.args.sep.value
        for row in page.iterRows(proc):
            response.write(sepChar.join(row), '\r\n')

class CSVPage(FabResource['CSVPage.Arguments', ProcT]):
    authenticator = LoginAuthPage.instance

    class Arguments(PageArgs):
        sep = EnumArg(Separator, Separator.COMMA)

    def getResponder(self, path: Optional[str], proc: ProcT) -> Responder:
        if path is None:
            return CSVResponder(self, proc)
        else:
            raise KeyError('Resource does not contain subitems')

    def errorResponder(self, ex: Exception, proc: PageProcessor) -> Responder:
        return plainTextErrorResponder

    def getFileName(self, proc: ProcT) -> str:
        raise NotImplementedError

    def iterRows(self, proc: ProcT) -> Iterator[Sequence[str]]:
        raise NotImplementedError

def presentCSVLink(page: str, args: CSVPage.Arguments) -> XML:
    return xhtml.p[
        'Export data in CSV format: ',
        pageLink(page, args.override(sep = Separator.COMMA))[ 'comma' ],
        ' or ',
        pageLink(page, args.override(sep = Separator.SEMICOLON))[ 'semicolon' ],
        ' separated',
        xhtml.br,
        'Note: Excel only accepts the list separator from the OS regional '
        'settings.'
        ]
